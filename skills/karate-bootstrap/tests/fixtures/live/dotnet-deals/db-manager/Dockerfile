FROM flyway/flyway:10.17.3-alpine
COPY sql /flyway/sql
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
