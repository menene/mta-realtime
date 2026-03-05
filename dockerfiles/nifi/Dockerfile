FROM apache/nifi:1.23.2
USER root
RUN mkdir -p /opt/nifi/nifi-current/drivers
RUN curl -fsSL \
    "https://jdbc.postgresql.org/download/postgresql-42.7.3.jar" \
    -o /opt/nifi/nifi-current/drivers/postgresql-42.7.3.jar && \
    chmod 644 /opt/nifi/nifi-current/drivers/postgresql-42.7.3.jar
# Patch: allow proxy host in non-secure (HTTP) mode behind reverse proxy
RUN sed -i '71,73d' /opt/nifi/scripts/start.sh
USER nifi
EXPOSE 8080
