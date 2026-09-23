#!/bin/sh
set -e

# ホストの .gitconfig が引き継がれない場合のみ設定する
git config --global --get user.name >/dev/null || git config --global user.name "JE6HUB"
git config --global --get user.email >/dev/null || git config --global user.email "kumagt2000@gmail.com"
git config --global --add safe.directory /app

pip install --no-cache-dir -r /app/requirements.txt

cd /app/my_website
python manage.py migrate --noinput
