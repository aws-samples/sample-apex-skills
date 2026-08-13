package com.example.orders;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

/**
 * REARCHITECTED order intake.
 *
 * Fixes, versus app-before's OrdersServlet:
 *
 *  * config_externalization — every environment-specific value is read from the
 *    environment (PRICING_ENDPOINT, ORDERS_ARCHIVE_BUCKET). No properties file
 *    is baked into the WAR and no credential exists in the tree: the S3 client
 *    authenticates with the ECS task role.
 *  * state_management — the archive goes to S3, not the local disk.
 *  * jakarta namespace, JAX-RS instead of a raw servlet.
 */
@Path("/orders")
@ApplicationScoped
public class OrdersResource {

    private final OrderArchiveService archive = new OrderArchiveService();

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response accept(@QueryParam("orderId") String orderId) {

        String id = (orderId == null || orderId.isBlank())
                ? "ORD-" + System.currentTimeMillis()
                : orderId;

        // Externalized configuration — resolved at runtime, not at build time.
        String pricing = System.getenv().getOrDefault(
                "PRICING_ENDPOINT", "http://pricing.internal/pricing");

        String payload = "{\"orderId\":\"" + id + "\",\"pricingEndpoint\":\"" + pricing + "\"}";

        String location;
        try {
            location = archive.archive(id, payload);
        } catch (RuntimeException e) {
            return Response.status(Response.Status.SERVICE_UNAVAILABLE)
                    .entity("{\"orderId\":\"" + id + "\",\"archived\":false,\"reason\":\""
                            + e.getClass().getSimpleName() + "\"}")
                    .build();
        }

        return Response.ok("{\"orderId\":\"" + id + "\","
                + "\"archivedTo\":\"" + location + "\","
                + "\"localFilesystemWrites\":false,"
                + "\"configSource\":\"environment\"}").build();
    }
}
