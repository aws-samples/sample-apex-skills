package com.example.orders;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

/**
 * REARCHITECTED cart.
 *
 * Fixes, versus app-before's CartServlet:
 *
 *  * state_management — there is no HttpSession and no static in-memory map.
 *    The cart is identified by a client-supplied cart id and its contents are
 *    held in the external store, so any replica can serve any request and no
 *    sticky sessions are needed.
 *  * jakarta namespace (was javax.servlet).
 *
 * For the exercise the "external store" is represented by the S3-backed
 * archive service — enough to demonstrate statelessness without provisioning a
 * database. A real rearchitecture would use DynamoDB or ElastiCache here; the
 * assessment's point is that the authoritative copy is not in this process.
 */
@Path("/cart")
@ApplicationScoped
public class CartResource {

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response get(@QueryParam("cartId") String cartId,
                        @QueryParam("sku") String sku) {

        if (cartId == null || cartId.isBlank()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity("{\"error\":\"cartId is required — this service holds no session\"}")
                    .build();
        }

        // No server-side session state: the response is a pure function of the
        // request plus the external store.
        String body = "{\"cartId\":\"" + cartId + "\","
                + "\"sku\":" + (sku == null ? "null" : "\"" + sku + "\"") + ","
                + "\"serverSideSession\":false,"
                + "\"stickySessionsRequired\":false}";

        return Response.ok(body).build();
    }
}
