# =============================================================================
# Rearchitect image for the MODERNIZED Orders app.
#
# Differences from app-before/Dockerfile, each one a Rearchitect outcome:
#
#  * Java 17 base image instead of Java 8 (off the EOL runtime)
#  * kernel-slim instead of full — only the features server.xml declares are
#    installed, which is what Liberty's composability buys you
#  * no mkdir of a local state directory: there is no local state
#  * runs as the non-root image user with a read-only-friendly layout
# =============================================================================
FROM icr.io/appcafe/open-liberty:kernel-slim-java17-openj9-ubi

# Server configuration first, so the feature installation below can read it.
COPY --chown=1001:0 src/main/liberty/config/server.xml /config/server.xml

# Install exactly the features server.xml declares.
RUN features.sh

COPY --chown=1001:0 target/orders.war /config/apps/orders.war

# Warm up the server's class cache for faster starts.
RUN configure.sh

EXPOSE 9080
