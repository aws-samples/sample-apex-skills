package com.example.orders;

import java.io.IOException;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.http.HttpSession;

/**
 * Shopping cart.
 *
 * PLANTED BLOCKERS (state_management):
 *
 *  1. The cart is stored in the HttpSession as the authoritative copy
 *     (session.setAttribute with a business object). With web.xml carrying no
 *     &lt;distributable/&gt; and no external session store configured, a second
 *     replica cannot see the cart and an instance replacement loses it.
 *
 *  2. ACTIVE_CARTS is a static in-memory map keyed by session id holding
 *     authoritative state — pervasive in-memory state, not a regenerable cache.
 */
@WebServlet(urlPatterns = {"/cart"})
public class CartServlet extends HttpServlet {

    private static final long serialVersionUID = 1L;

    /**
     * PLANTED: static singleton map keyed by session id. This is the
     * authoritative record of who has what in flight; nothing external holds it.
     */
    private static final Map<String, List<String>> ACTIVE_CARTS =
            Collections.synchronizedMap(new HashMap<String, List<String>>());

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        HttpSession session = request.getSession(true);

        @SuppressWarnings("unchecked")
        List<String> cart = (List<String>) session.getAttribute("cart");
        if (cart == null) {
            cart = new ArrayList<String>();
            // PLANTED: business object into the session as the authoritative copy.
            session.setAttribute("cart", cart);
        }

        String sku = request.getParameter("sku");
        if (sku != null && !sku.isEmpty()) {
            cart.add(sku);
            ACTIVE_CARTS.put(session.getId(), cart);
        }

        response.setContentType("application/json; charset=UTF-8");
        PrintWriter out = response.getWriter();
        out.print("{\"sessionId\":\"" + session.getId() + "\",\"items\":" + cart.size()
                + ",\"activeCarts\":" + ACTIVE_CARTS.size() + "}");
        out.flush();
    }
}
