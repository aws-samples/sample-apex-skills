package com.example.orders;

import java.io.IOException;
import java.io.PrintWriter;

import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

/**
 * Liveness endpoint for the ALB target group.
 *
 * Deliberately trivial: it reports that the servlet container is serving, with
 * no dependency check. That is enough for the exercise's health check and keeps
 * the planted blockers as the only interesting findings.
 */
@WebServlet(urlPatterns = {"/health"})
public class HealthServlet extends HttpServlet {

    private static final long serialVersionUID = 1L;

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("application/json; charset=UTF-8");
        PrintWriter out = response.getWriter();
        out.print("{\"status\":\"UP\"}");
        out.flush();
    }
}
