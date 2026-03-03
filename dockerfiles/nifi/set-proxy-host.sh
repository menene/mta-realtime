#!/bin/bash
# Wait for nifi.properties to be generated, then patch proxy host
(
  while [ ! -f /opt/nifi/nifi-current/conf/nifi.properties ]; do
    sleep 2
  done
  sleep 5
  if [ -n "$NIFI_WEB_PROXY_HOST" ]; then
    sed -i "s|nifi.web.proxy.host=.*|nifi.web.proxy.host=${NIFI_WEB_PROXY_HOST}|" /opt/nifi/nifi-current/conf/nifi.properties
    echo "Set nifi.web.proxy.host=${NIFI_WEB_PROXY_HOST}"
  fi
) &

exec ../scripts/start.sh
