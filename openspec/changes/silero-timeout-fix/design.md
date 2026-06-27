# Silero Timeout Fix — Design

## 修复

`silero_download_timeout` 默认值从 15s → 60s。模型首次下载 ~45MB，慢速网络需要 30-60s。缓存后不再需要下载。
