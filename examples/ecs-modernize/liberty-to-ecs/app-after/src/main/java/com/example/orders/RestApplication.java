package com.example.orders;

import jakarta.ws.rs.ApplicationPath;
import jakarta.ws.rs.core.Application;

/** JAX-RS activation — no web.xml servlet wiring needed. */
@ApplicationPath("/api")
public class RestApplication extends Application {
}
