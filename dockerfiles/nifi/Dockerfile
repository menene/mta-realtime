FROM apache/nifi:1.23.2
USER root
RUN mkdir -p /opt/nifi/nifi-current/drivers
RUN curl -fsSL \
    "https://jdbc.postgresql.org/download/postgresql-42.7.3.jar" \
    -o /opt/nifi/nifi-current/drivers/postgresql-42.7.3.jar && \
    chmod 644 /opt/nifi/nifi-current/drivers/postgresql-42.7.3.jar
COPY set-proxy-host.sh /opt/nifi/scripts/set-proxy-host.sh
RUN chmod +x /opt/nifi/scripts/set-proxy-host.sh
USER nifi
EXPOSE 8080
ENTRYPOINT ["/opt/nifi/scripts/set-proxy-host.sh"]
