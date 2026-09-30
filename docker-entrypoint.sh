#!/bin/sh
set -e

python manage.py migrate --noinput
# 翻訳ファイル (.po) を .mo にコンパイルする (.mo は git 管理外)
python manage.py compilemessages --ignore=.venv
python manage.py collectstatic --noinput

exec "$@"
