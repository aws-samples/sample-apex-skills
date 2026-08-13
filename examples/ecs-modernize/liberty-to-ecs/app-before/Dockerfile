# =============================================================================
# Replatform ("containerize as-is") image for the LEGACY Orders app.
#
# This Dockerfile is what the Replatform path produces: the application code is
# not changed, the existing Liberty server.xml is carried over verbatim, and the
# base image matches the app's current coordinates (Java 8, Java EE 7).
#
# It deliberately does NOT fix any planted blocker. Version parity is the point:
# the code is not changing, so the runtime must not either.
#
# Base image: Open Liberty on UBI with Java 8 (OpenJ9), which is the version
# parity match for this app. Pinned by digest-less floating tag for exercise
# readability; pin to a dated tag for anything real.
# =============================================================================
FROM icr.io/appcafe/open-liberty:full-java8-openj9-ubi

# The legacy server.xml, carried over unchanged from the VM.
COPY --chown=1001:0 src/main/liberty/config/server.xml /config/server.xml

# The application, built by scripts/build.sh.
COPY --chown=1001:0 target/orders.war /config/apps/orders.war

# The app writes its order archive to a hardcoded absolute path. On the VM this
# was a normal directory; here we create it so the container starts, which is
# what makes the blocker observable at runtime instead of at startup: the
# directory exists but is ephemeral, so archives vanish on task replacement.
USER root
RUN mkdir -p /opt/was/orders/archive \
    && chown -R 1001:0 /opt/was/orders \
    && chmod -R g+rw /opt/was/orders
USER 1001

EXPOSE 9080

# Open Liberty's own entrypoint runs the server in the foreground.
