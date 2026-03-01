FROM apache/superset:3.1.3
USER root
RUN pip install --no-cache-dir psycopg2-binary==2.9.9
COPY --chown=superset:superset superset_config.py /app/pythonpath/superset_config.py
COPY --chown=superset:superset docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh && \
    chmod 644 /app/pythonpath/superset_config.py
USER superset
EXPOSE 8088
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
