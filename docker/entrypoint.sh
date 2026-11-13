#!/bin/sh
# 容器啟動時執行：套用 migration；正式模式下收集靜態檔。
# collectstatic 不能在 image build 時跑：settings 與 AccountsConfig.ready()
# 需要完整的環境變數（SECRET_KEY、OAuth 設定）才肯啟動。
set -e

python manage.py migrate --noinput

if [ "$DJANGO_DEBUG" != "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
