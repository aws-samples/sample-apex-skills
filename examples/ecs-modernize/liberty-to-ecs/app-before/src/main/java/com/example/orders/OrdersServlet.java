package com.example.orders;

import java.io.IOException;
import java.io.InputStream;
import java.io.PrintWriter;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;

import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

/**
 * Accepts an order and archives it.
 *
 * PLANTED BLOCKERS:
 *
 *  1. (config_externalization) Configuration is read from the properties file
 *     baked into the WAR — endpoints and the credential travel inside the
 *     artifact, so the same build cannot move across environments.
 *
 *  2. (state_management) Every accepted order is written to the local
 *     filesystem via OrderArchiveService.
 */
@WebServlet(urlPatterns = {"/orders"})
public class OrdersServlet extends HttpServlet {

    private static final long serialVersionUID = 1L;
    private static final Logger LOG = Logger.getLogger(OrdersServlet.class.getName());

    private final Properties config = new Properties();
    private final OrderArchiveService archive = new OrderArchiveService();

    @Override
    public void init() throws ServletException {
        // PLANTED: config comes from inside the deployable artifact.
        InputStream in = getClass().getClassLoader()
                .getResourceAsStream("application.properties");
        if (in == null) {
            throw new ServletException("application.properties missing from the WAR");
        }
        try {
            config.load(in);
        } catch (IOException e) {
            throw new ServletException("cannot read application.properties", e);
        } finally {
            try {
                in.close();
            } catch (IOException ignored) {
                // nothing useful to do
            }
        }
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        String orderId = request.getParameter("orderId");
        if (orderId == null || orderId.isEmpty()) {
            orderId = "ORD-" + System.currentTimeMillis();
        }

        // PLANTED (build_reproducibility): calls into the unmanaged JAR that
        // pom.xml pulls in with `system` scope from lib/. A system-scoped
        // dependency is not packaged into the WAR either, so the class is
        // present at compile time and absent at runtime — hence the reflective
        // lookup and the graceful fallback below. That mismatch is itself the
        // finding: the build is not reproducible and the artifact is incomplete.
        String taxRate;
        try {
            Class<?> rules = Class.forName("com.example.tax.TaxRules");
            Object rate = rules.getMethod("rateFor", String.class).invoke(null, "JP");
            taxRate = String.valueOf(rate);
        } catch (ReflectiveOperationException | LinkageError e) {
            LOG.log(Level.WARNING, "legacy-tax-rules not on the runtime classpath", e);
            taxRate = "unavailable";
        }

        String payload = "{\"orderId\":\"" + orderId + "\","
                + "\"taxRate\":\"" + taxRate + "\","
                + "\"pricingEndpoint\":\"" + config.getProperty("pricing.service.endpoint") + "\"}";

        String archived;
        try {
            // PLANTED: local-filesystem state write.
            archive.archive(orderId, payload);
            archived = "true";
        } catch (IOException e) {
            // The archive directory is not writable in a container running as
            // non-root — the failure is reported rather than hidden, so the
            // exercise shows the blocker biting at runtime.
            LOG.log(Level.WARNING, "archive failed for " + orderId, e);
            archived = "false (" + e.getClass().getSimpleName() + ")";
        }

        response.setContentType("application/json; charset=UTF-8");
        PrintWriter out = response.getWriter();
        out.print("{\"orderId\":\"" + orderId + "\","
                + "\"taxRate\":\"" + taxRate + "\","
                + "\"archivedLocally\":\"" + archived + "\","
                + "\"dbUrl\":\"" + config.getProperty("orders.db.url") + "\","
                + "\"mqConnectionMode\":\"" + config.getProperty("orders.mq.connectionMode") + "\"}");
        out.flush();
    }
}
