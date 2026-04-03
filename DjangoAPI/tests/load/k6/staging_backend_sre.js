import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || '').replace(/\/$/, '');
const PROFILE = (__ENV.PROFILE || 'smoke').toLowerCase(); // smoke | normal | burst
const TARGET_MODE = (__ENV.TARGET_MODE || 'rembg').toLowerCase(); // rembg | exhibit

// shallow health check に変更
const HEALTH_PATH = __ENV.HEALTH_PATH || '/healthz';
const GUEST_GALLERY_PATH = __ENV.GUEST_GALLERY_PATH || '/api/guest/gallery/';
const GUEST_ID = __ENV.GUEST_ID || '';
const REMBG_PATH = __ENV.REMBG_PATH || '/api/image/rembg/isnet-general-use';
const REMBG_IMAGE_URL = __ENV.REMBG_IMAGE_URL || '';

const EXHIBIT_GALLERY_ID = __ENV.EXHIBIT_GALLERY_ID || '';
const EXHIBIT_SLOT_INDEX = Number(__ENV.EXHIBIT_SLOT_INDEX || '0');
const EXHIBIT_BODY_JSON = __ENV.EXHIBIT_BODY_JSON || '';

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

if (!BASE_URL) throw new Error('BASE_URL is required');
if (!profiles[PROFILE]) throw new Error(`Unsupported PROFILE: ${PROFILE}`);
if (!['rembg', 'exhibit'].includes(TARGET_MODE)) {
  throw new Error(`Unsupported TARGET_MODE: ${TARGET_MODE}`);
}
if (!GUEST_ID) {
  throw new Error('GUEST_ID is required because guest endpoints require X-Guest-Id');
}
if (TARGET_MODE === 'rembg' && !REMBG_IMAGE_URL) {
  throw new Error('REMBG_IMAGE_URL is required when TARGET_MODE=rembg');
}
if (TARGET_MODE === 'exhibit' && !EXHIBIT_GALLERY_ID) {
  throw new Error('EXHIBIT_GALLERY_ID is required when TARGET_MODE=exhibit');
}
if (TARGET_MODE === 'exhibit' && !EXHIBIT_BODY_JSON) {
  throw new Error('EXHIBIT_BODY_JSON is required when TARGET_MODE=exhibit');
}

const healthLatency = new Trend('health_latency', true);
const galleryLatency = new Trend('gallery_latency', true);
const targetLatency = new Trend('target_latency', true);

const healthErrorRate = new Rate('health_error_rate');
const galleryErrorRate = new Rate('gallery_error_rate');
const targetErrorRate = new Rate('target_error_rate');
const timeoutRate = new Rate('timeout_rate');

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
    timeout_rate: ['rate<0.05'],
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

function isTimeout(res) {
  return (
    res &&
    (res.error_code === 1050 ||
      String(res.error || '').toLowerCase().includes('timeout'))
  );
}

function recordCommon(latencyMetric, counterMetric, res) {
  counterMetric.add(1);
  latencyMetric.add(res.timings.duration);
  timeoutRate.add(isTimeout(res) ? 1 : 0);
}

function hitHealth() {
  const res = http.get(`${BASE_URL}${HEALTH_PATH}`, {
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'healthz' },
  });

  recordCommon(healthLatency, healthRequests, res);

  const failed = !res || res.status !== 200 || !!res.error;
  healthErrorRate.add(failed ? 1 : 0);

  check(res, {
    'healthz status is 200': (r) => r.status === 200,
  });

  return res;
}

function hitGallery() {
  const res = http.get(`${BASE_URL}${GUEST_GALLERY_PATH}`, {
    headers: { 'X-Guest-Id': GUEST_ID },
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'gallery_get' },
  });

  recordCommon(galleryLatency, galleryRequests, res);

  const failed = !res || res.status >= 400 || !!res.error;
  galleryErrorRate.add(failed ? 1 : 0);

  check(res, {
    'gallery_get status is 200': (r) => r.status === 200,
  });

  return res;
}

function hitRembg() {
  const payload = JSON.stringify({
    image_url: REMBG_IMAGE_URL,
  });

  const res = http.post(`${BASE_URL}${REMBG_PATH}`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'X-Guest-Id': GUEST_ID,
    },
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'rembg' },
  });

  recordCommon(targetLatency, targetRequests, res);

  const failed = !res || res.status >= 400 || !!res.error;
  targetErrorRate.add(failed ? 1 : 0);

  check(res, {
    'rembg status is 200': (r) => r.status === 200,
  });

  return res;
}

function hitExhibitUpsert() {
  const path = `/api/galleries/${EXHIBIT_GALLERY_ID}/exhibits/${EXHIBIT_SLOT_INDEX}/`;

  const res = http.put(`${BASE_URL}${path}`, EXHIBIT_BODY_JSON, {
    headers: {
      'Content-Type': 'application/json',
      'X-Guest-Id': GUEST_ID,
    },
    timeout: REQUEST_TIMEOUT,
    tags: { endpoint: 'exhibit_upsert' },
  });

  recordCommon(targetLatency, targetRequests, res);

  const ok = res && (res.status === 200 || res.status === 201);
  const failed = !ok || !!res.error;
  targetErrorRate.add(failed ? 1 : 0);

  check(res, {
    'exhibit_upsert status is 200 or 201': (r) =>
      r.status === 200 || r.status === 201,
  });

  return res;
}

export default function () {
  hitHealth();
  hitGallery();

  if (TARGET_MODE === 'rembg') {
    hitRembg();
  } else {
    hitExhibitUpsert();
  }

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
    '| endpoint | req count | approx req/s | p50 latency(ms) | p95 latency(ms) | error rate |',
    '|---|---:|---:|---:|---:|---:|',
    `| healthz | ${healthReqCount} | ${fmt(healthReqCount / totalSeconds)} | ${fmt(metricValues(data, 'health_latency')['p(50)'])} | ${fmt(metricValues(data, 'health_latency')['p(95)'])} | ${fmt((metricValues(data, 'health_error_rate').rate || 0) * 100)}% |`,
    `| gallery_get | ${galleryReqCount} | ${fmt(galleryReqCount / totalSeconds)} | ${fmt(metricValues(data, 'gallery_latency')['p(50)'])} | ${fmt(metricValues(data, 'gallery_latency')['p(95)'])} | ${fmt((metricValues(data, 'gallery_error_rate').rate || 0) * 100)}% |`,
    `| ${targetLabel} | ${targetReqCount} | ${fmt(targetReqCount / totalSeconds)} | ${fmt(metricValues(data, 'target_latency')['p(50)'])} | ${fmt(metricValues(data, 'target_latency')['p(95)'])} | ${fmt((metricValues(data, 'target_error_rate').rate || 0) * 100)}% |`,
    '',
    '## Notes',
    '',
    '- /healthz is treated as a shallow connectivity/liveness check.',
    '- req/s is approximated as request_count / planned_duration_sec.',
    `- rembg endpoint accepts image_url in request JSON.`, 
    `- exhibit upsert uses PUT /api/galleries/{gallery_id}/exhibits/{slot_index}/ and image_original_url is required.`,
    '',
  ].join('\n');

  return {
    stdout: md,
    [`k6-summary-${PROFILE}-${TARGET_MODE}.json`]: JSON.stringify(data, null, 2),
    [`k6-summary-${PROFILE}-${TARGET_MODE}.md`]: md,
  };
}