# Build a separate image; never rebuild the running VM container or its volume.
FROM postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3

# The official image configures the signed PGDG apt repository. Pin all three
# packages: pgvector's later +2 build would require a newer PostgreSQL server.
RUN apt-get update \
    && apt-get install -y --no-remove --no-install-recommends \
        postgresql-17-pgvector=0.8.7-1.pgdg12+1 \
        postgresql-17=17.6-2.pgdg12+1 \
        postgresql-client-17=17.6-2.pgdg12+1 \
    && test "$(pg_config --version)" = "PostgreSQL 17.6 (Debian 17.6-2.pgdg12+1)" \
    && test "$(dpkg-query -W -f='${Version}' postgresql-17-pgvector)" = '0.8.7-1.pgdg12+1' \
    && rm -rf /var/lib/apt/lists/*
