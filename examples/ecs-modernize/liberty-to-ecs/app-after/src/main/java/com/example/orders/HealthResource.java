package com.example.orders;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

/** Liveness endpoint for the ALB target group. */
@Path("/health")
@ApplicationScoped
public class HealthResource {

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response get() {
        return Response.ok("{\"status\":\"UP\"}").build();
    }
}
