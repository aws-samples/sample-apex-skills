package com.example.orders;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.text.SimpleDateFormat;
import java.util.Date;

/**
 * Writes a durable record of every accepted order.
 *
 * PLANTED BLOCKERS:
 *
 *  1. (state_management / local_state) Business data is persisted to a fixed
 *     local filesystem path. Container filesystems are ephemeral, so these
 *     archives vanish on task replacement and are invisible to other replicas.
 *     This is NOT log output — it is the durable order record.
 *
 *  2. (os_host_dependency) The path is a hardcoded, OS-specific absolute path
 *     using a Linux-only layout under /opt/was.
 */
public class OrderArchiveService {

    /**
     * PLANTED: hardcoded OS-specific absolute path to a state directory.
     */
    private static final String ARCHIVE_DIR = "/opt/was/orders/archive";

    public void archive(String orderId, String payload) throws IOException {
        File dir = new File(ARCHIVE_DIR);
        if (!dir.exists() && !dir.mkdirs()) {
            throw new IOException("cannot create archive dir: " + ARCHIVE_DIR);
        }

        String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss").format(new Date());
        File target = new File(dir, orderId + "-" + stamp + ".json");

        // PLANTED: authoritative business data written to the local disk.
        Writer w = new OutputStreamWriter(new FileOutputStream(target, true), "UTF-8");
        try {
            w.write(payload);
        } finally {
            w.close();
        }
    }
}
