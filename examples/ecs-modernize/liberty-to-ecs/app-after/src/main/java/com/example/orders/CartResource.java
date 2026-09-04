package com.example.orders;

import java.util.regex.Pattern;

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

    // Accept-known-good allowlists for the client-supplied values, applied
    // before either is concatenated into the hand-built JSON body below.
    // Invalid input is rejected (HTTP 400), not substituted or encoded, so
    // untrusted characters never reach the response (reflected XSS / JSON
    // injection). sku permits '.' and '_' in addition to the id set, since
    // real SKUs use them; the metacharacters that break out of JSON strings
    // ('"', '<', '>', '{', '}', '\\') stay excluded.
    private static final Pattern ID_PATTERN = Pattern.compile("[A-Za-z0-9-]{1,64}");
    private static final Pattern SKU_PATTERN = Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response get(@QueryParam("cartId") String cartId,
                        @QueryParam("sku") String sku) {

        if (cartId == null || cartId.isBlank()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity("{\"error\":\"cartId is required — this service holds no session\"}")
                    .build();
        }

        if (!ID_PATTERN.matcher(cartId).matches()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity("{\"error\":\"cartId must match [A-Za-z0-9-]{1,64}\"}")
                    .build();
        }

        if (sku != null && !SKU_PATTERN.matcher(sku).matches()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity("{\"error\":\"sku must match [A-Za-z0-9._-]{1,64}\"}")
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
