from storages.backends.s3boto3 import S3Boto3Storage

class StaticStorage(S3Boto3Storage):
    location = 'static'
    default_acl = 'public-read' # 静的ファイルは公開

class MediaStorage(S3Boto3Storage):
    location = 'media'
    default_acl = 'private' # メディアファイルは非公開（Presigned URLでアクセス制御するなら）
    file_overwrite = False