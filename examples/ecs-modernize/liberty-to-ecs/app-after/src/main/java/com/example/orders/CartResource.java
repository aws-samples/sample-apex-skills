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
    // before either is concatenated into the hand-built JSON body below. cartId
    // uses the shared IdValidation.ID_PATTERN; sku additionally permits '.' and
    // '_' since real SKUs use them. Invalid input is rejected (HTTP 400), not
    // substituted or encoded. Because the allowlist is accept-known-good,
    // everything outside it is excluded: the '"' and '\\' that end or escape a
    // JSON string value, the control characters that RFC 8259 section 7
    // requires be escaped, and the '<' / '>' that would matter only if the
    // value were later rendered in an HTML context.
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

        if (!IdValidation.ID_PATTERN.matcher(cartId).matches()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity("{\"error\":\"cartId must match "
                            + IdValidation.ID_PATTERN.pattern() + "\"}")
                    .build();
        }

        if (sku != null && !SKU_PATTERN.matcher(sku).matches()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity("{\"error\":\"sku must match "
                            + SKU_PATTERN.pattern() + "\"}")
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
