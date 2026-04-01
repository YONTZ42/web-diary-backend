import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || 'https://api-staging.memocho.link').replace(/\/$/, '');
const PROFILE = (__ENV.PROFILE || 'smoke').toLowerCase(); // smoke | normal | burst
const TARGET_MODE = (__ENV.TARGET_MODE || 'rembg').toLowerCase(); // rembg | exhibit
const HEALTH_PATH = __ENV.HEALTH_PATH || '/healthz';
const GUEST_ISSUE_PATH = __ENV.GUEST_ISSUE_PATH || '/api/auth/guest/';
const GALLERY_GET_PATH = __ENV.GALLERY_GET_PATH || '/api/guest/gallery/';
const GALLERY_POST_PATH = __ENV.GALLERY_POST_PATH || '/api/guest/gallery/';
const REMBG_PATH = __ENV.REMBG_PATH || '/api/image/rembg/isnet-general-use';
const EXHIBIT_GALLERY_ID = __ENV.EXHIBIT_GALLERY_ID || '';
const EXHIBIT_SLOT_INDEX = Number(__ENV.EXHIBIT_SLOT_INDEX || '0');
const EXHIBIT_UPSERT_PATH = __ENV.EXHIBIT_UPSERT_PATH || '';
const EXHIBIT_BODY_JSON = __ENV.EXHIBIT_BODY_JSON || '';
const REMBG_IMAGE_URL = __ENV.REMBG_IMAGE_URL || '';
const THINK_TIME_MS = Number(__ENV.THINK_TIME_MS || '300');
const REQUEST_TIMEOUT = __ENV.REQUEST_TIMEOUT || '30s';
const INSECURE_SKIP_TLS = (__ENV.INSECURE_SKIP_TLS || 'false').toLowerCase() === 'true';

const profiles = {
  smoke: {
    vus: [
      { duration: '20s', target: 1 },
      { duration: '40s', target: 5 },
      { duration: '20s', target: 1 },
    ],
    totalSeconds: 80,
  },
  normal: {
    vus: [
      { duration: '30s', target: 10 },
      { duration: '60s', target: 20 },
      { duration: '30s', target: 10 },
    ],
    totalSeconds: 120,
  },
  burst: {
    vus: [
      { duration: '10s', target: 30 },
      { duration: '20s', target: 50 },
      { duration: '10s', target: 30 },
    ],
    totalSeconds: 40,
  },
};

if (!BASE_URL) {
  throw new Error('BASE_URL is required');
}
if (!profiles[PROFILE]) {
  throw new Error(`Unsupported PROFILE: ${PROFILE}`);
}
if (!['rembg', 'exhibit'].includes(TARGET_MODE)) {
  throw new Error(`Unsupported TARGET_MODE: ${TARGET_MODE}`);
}
if (TARGET_MODE === 'rembg' && !REMBG_IMAGE_URL) {
  throw new Error('REMBG_IMAGE_URL is required when TARGET_MODE=rembg');
}
if (TARGET_MODE === 'exhibit' && !EXHIBIT_BODY_JSON) {
  throw new Error('EXHIBIT_BODY_JSON is required when TARGET_MODE=exhibit');
}

const healthLatency = new Trend('health_latency', true);
const galleryLatency = new Trend('gallery_latency', true);
const targetLatency = new Trend('target_latency', true);

const healthErrors = new Rate('health_error_rate');
const galleryErrors = new Rate('gallery_error_rate');
const targetErrors = new Rate('target_error_rate');

const healthTimeouts = new Rate('health_timeout_rate');
const galleryTimeouts = new Rate('gallery_timeout_rate');
const targetTimeouts = new Rate('target_timeout_rate');

const healthRequests = new Counter('health_requests');
const galleryRequests = new Counter('gallery_requests');
const targetRequests = new Counter('target_requests');

export const options = {
  insecureSkipTLSVerify: INSECURE_SKIP_TLS,
  summaryTrendStats: ['avg', 'med', 'p(50)', 'p(95)', 'min', 'max'],
  thresholds: {
    health_error_rate: ['rate<0.01'],
    gallery_error_rate: ['rate<0.01'],
    target_error_rate: ['rate<0.05'],
    health_timeout_rate: ['rate<0.01'],
    gallery_timeout_rate: ['rate<0.01'],
    target_timeout_rate: ['rate<0.05'],
  },
  scenarios: {
    backend_sre: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: profiles[PROFILE].vus,
      gracefulRampDown: '5s',
      tags: { profile: PROFILE, target_mode: TARGET_MODE },
    },
  },
};

function getGuestIdFromResponse(res) {
  let body = {};
  try {
    body = res.json();
  } catch (_) {
    body = {};
  }
  return body.guest_id || body.guestId || body.id || null;
}

export function setup() {
  const setupData = {
    baseUrl: BASE_URL,
    profile: PROFILE,
    targetMode: TARGET_MODE,
    guestId: __ENV.GUEST_ID || null,
    galleryId: __ENV.GALLERY_ID || null,
    exhibitPath: EXHIBIT_UPSERT_PATH || null,
  };

  if (!setupData.guestId) {
    const guestRes = http.post(`${BASE_URL}${GUEST_ISSUE_PATH}`, null, {
      timeout: REQUEST_TIMEOUT,
      tags: { endpoint: 'guest_issue' },
    });

    check(guestRes, {
      'setup guest issue status is 200': (r) => r.status === 200,
    });

    const guestId = getGuestIdFromResponse(guestRes);
    if (!guestId) {
      throw new Error(`Failed to obtain guest_id from ${GUEST_ISSUE_PATH}`);
    }
    setupData.guestId = guestId;
  }

  const authHeaders = {
    'X-Guest-Id': setupData.guestId,
  };

  const galleryRes = http.post(`${BASE_URL}${GALLERY_POST_PATH}`, null, {
    headers: authHeaders,
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'gallery_prepare' },
  });

  check(galleryRes, {
    'setup gallery prepare status is 200 or 201': (r) =>
      r.status === 200 || r.status === 201,
  });

  let galleryBody = {};
  try {
    galleryBody = galleryRes.json();
  } catch (_) {
    galleryBody = {};
  }

  if (!setupData.galleryId) {
    setupData.galleryId = galleryBody.id || galleryBody.gallery_id || null;
  }

  if (TARGET_MODE === 'exhibit') {
    if (!setupData.galleryId && !EXHIBIT_GALLERY_ID) {
      throw new Error('gallery_id is required for exhibit mode');
    }
    setupData.galleryId = EXHIBIT_GALLERY_ID || setupData.galleryId;
    setupData.exhibitPath =
      EXHIBIT_UPSERT_PATH ||
      `/api/galleries/${setupData.galleryId}/exhibits/${EXHIBIT_SLOT_INDEX}/`;
  }

  return setupData;
}

function recordResult(metricSet, res, endpointName) {
  metricSet.requests.add(1);
  metricSet.latency.add(res.timings.duration);

  const timeout =
    res.error_code === 1050 ||
    String(res.error || '').toLowerCase().includes('timeout');

  metricSet.timeouts.add(timeout ? 1 : 0);

  const failed = !res || res.status >= 400 || !!res.error;
  metricSet.errors.add(failed ? 1 : 0);

  check(res, {
    [`${endpointName} status < 400`]: (r) => r.status < 400,
  });
}

function hitHealth(data) {
  const res = http.get(`${data.baseUrl}${HEALTH_PATH}`, {
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'health' },
  });

  recordResult(
    {
      requests: healthRequests,
      latency: healthLatency,
      errors: healthErrors,
      timeouts: healthTimeouts,
    },
    res,
    'health'
  );
}

function hitGallery(data) {
  const res = http.get(`${data.baseUrl}${GALLERY_GET_PATH}`, {
    headers: { 'X-Guest-Id': data.guestId },
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'gallery_get' },
  });

  recordResult(
    {
      requests: galleryRequests,
      latency: galleryLatency,
      errors: galleryErrors,
      timeouts: galleryTimeouts,
    },
    res,
    'gallery'
  );
}

function hitTarget(data) {
  if (data.targetMode === 'rembg') {
    const payload = JSON.stringify({ image_url: REMBG_IMAGE_URL });

    const res = http.post(`${data.baseUrl}${REMBG_PATH}`, payload, {
      headers: {
        'Content-Type': 'application/json',
        'X-Guest-Id': data.guestId,
      },
      timeout: REQUEST_TIMEOUT,
      tags: { endpoint: 'rembg' },
    });

    recordResult(
      {
        requests: targetRequests,
        latency: targetLatency,
        errors: targetErrors,
        timeouts: targetTimeouts,
      },
      res,
      'rembg'
    );
    return;
  }

  const payload = EXHIBIT_BODY_JSON;

  const res = http.put(`${data.baseUrl}${data.exhibitPath}`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'X-Guest-Id': data.guestId,
    },
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'exhibit_upsert' },
  });

  recordResult(
    {
      requests: targetRequests,
      latency: targetLatency,
      errors: targetErrors,
      timeouts: targetTimeouts,
    },
    res,
    'exhibit_upsert'
  );
}

export default function (data) {
  hitHealth(data);
  hitGallery(data);
  hitTarget(data);
  sleep(THINK_TIME_MS / 1000);
}

function fmt(v, digits = 2) {
  if (v === undefined || v === null || Number.isNaN(v)) return '-';
  return Number(v).toFixed(digits);
}

function metricValues(data, key) {
  return data.metrics[key] && data.metrics[key].values
    ? data.metrics[key].values
    : {};
}

export function handleSummary(data) {
  const totalSeconds = profiles[PROFILE].totalSeconds;
  const healthReqCount = metricValues(data, 'health_requests').count || 0;
  const galleryReqCount = metricValues(data, 'gallery_requests').count || 0;
  const targetReqCount = metricValues(data, 'target_requests').count || 0;
  const targetLabel = TARGET_MODE === 'rembg' ? 'rembg' : 'exhibit_upsert';

  const md = [
    '# k6 Load Test Result',
    '',
    `- base_url: ${BASE_URL}`,
    `- profile: ${PROFILE}`,
    `- target_mode: ${TARGET_MODE}`,
    `- planned_duration_sec: ${totalSeconds}`,
    `- request_timeout: ${REQUEST_TIMEOUT}`,
    '',
    '## Endpoint Summary',
    '',
    '| endpoint | req count | approx req/s | p50 latency(ms) | p95 latency(ms) | error rate | timeout rate |',
    '|---|---:|---:|---:|---:|---:|---:|',
    `| health | ${healthReqCount} | ${fmt(
      healthReqCount / totalSeconds
    )} | ${fmt(metricValues(data, 'health_latency')['p(50)'])} | ${fmt(
      metricValues(data, 'health_latency')['p(95)']
    )} | ${fmt((metricValues(data, 'health_error_rate').rate || 0) * 100)}% | ${fmt(
      (metricValues(data, 'health_timeout_rate').rate || 0) * 100
    )}% |`,
    `| gallery_get | ${galleryReqCount} | ${fmt(
      galleryReqCount / totalSeconds
    )} | ${fmt(metricValues(data, 'gallery_latency')['p(50)'])} | ${fmt(
      metricValues(data, 'gallery_latency')['p(95)']
    )} | ${fmt((metricValues(data, 'gallery_error_rate').rate || 0) * 100)}% | ${fmt(
      (metricValues(data, 'gallery_timeout_rate').rate || 0) * 100
    )}% |`,
    `| ${targetLabel} | ${targetReqCount} | ${fmt(
      targetReqCount / totalSeconds
    )} | ${fmt(metricValues(data, 'target_latency')['p(50)'])} | ${fmt(
      metricValues(data, 'target_latency')['p(95)']
    )} | ${fmt((metricValues(data, 'target_error_rate').rate || 0) * 100)}% | ${fmt(
      (metricValues(data, 'target_timeout_rate').rate || 0) * 100
    )}% |`,
    '',
    '## Threshold Result',
    '',
    `- health_error_rate < 1%: ${
      (metricValues(data, 'health_error_rate').rate || 0) < 0.01
        ? 'PASS'
        : 'FAIL'
    }`,
    `- gallery_error_rate < 1%: ${
      (metricValues(data, 'gallery_error_rate').rate || 0) < 0.01
        ? 'PASS'
        : 'FAIL'
    }`,
    `- target_error_rate < 5%: ${
      (metricValues(data, 'target_error_rate').rate || 0) < 0.05
        ? 'PASS'
        : 'FAIL'
    }`,
    `- health_timeout_rate < 1%: ${
      (metricValues(data, 'health_timeout_rate').rate || 0) < 0.01
        ? 'PASS'
        : 'FAIL'
    }`,
    `- gallery_timeout_rate < 1%: ${
      (metricValues(data, 'gallery_timeout_rate').rate || 0) < 0.01
        ? 'PASS'
        : 'FAIL'
    }`,
    `- target_timeout_rate < 5%: ${
      (metricValues(data, 'target_timeout_rate').rate || 0) < 0.05
        ? 'PASS'
        : 'FAIL'
    }`,
    '',
    '## Notes',
    '',
    '- req/s is approximated as request_count / planned_duration_sec.',
    '- For staging validation, compare these results with CloudWatch App Runner latency/5xx and rembg structured logs.',
    '',
  ].join('\n');

  return {
    stdout: md,
    [`k6-summary-${PROFILE}-${TARGET_MODE}.json`]: JSON.stringify(data, null, 2),
    [`k6-summary-${PROFILE}-${TARGET_MODE}.md`]: md,
  };
}