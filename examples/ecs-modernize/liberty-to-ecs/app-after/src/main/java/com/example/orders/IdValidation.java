package com.example.orders;

import java.util.regex.Pattern;

/**
 * Shared accept-known-good allowlist for client-supplied identifiers.
 *
 * Kept in one place so the resources and the archive service validate against
 * the same rule: widening the allowlist in one call site can no longer drift
 * from the others (which would let a value the resource accepts be rejected by
 * the archive guard, or vice versa). Error messages are built from
 * {@code ID_PATTERN.pattern()} for the same reason.
 */
final class IdValidation {

    /** Order and cart ids: 1-64 characters of ASCII letters, digits, and hyphen. */
    static final Pattern ID_PATTERN = Pattern.compile("[A-Za-z0-9-]{1,64}");

    private IdValidation() {
    }
}
