package com.example.orders;

import java.time.Instant;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * REARCHITECTED: order archives go to Amazon S3.
 *
 * Fixes, versus app-before:
 *
 *  * state_management — no local filesystem write. The archive lives in an
 *    external store, so it survives task replacement and every replica sees it.
 *  * os_host_dependency — the hardcoded /opt/was absolute path is gone.
 *  * config_externalization — the bucket name comes from the environment
 *    (ORDERS_ARCHIVE_BUCKET), and the region and credentials come from the
 *    default provider chain, which on ECS resolves to the task role. No
 *    endpoint or secret is baked into the artifact.
 */
public class OrderArchiveService {

    private final S3Client s3;
    private final String bucket;

    public OrderArchiveService() {
        this.bucket = System.getenv("ORDERS_ARCHIVE_BUCKET");
        // Region and credentials resolve from the default chain: on ECS that is
        // the task's region and the task role — nothing to configure in code.
        this.s3 = S3Client.create();
    }

    /** Visible for the local unit test, which injects a stub client. */
    OrderArchiveService(S3Client s3, String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public boolean isConfigured() {
        return bucket != null && !bucket.isEmpty();
    }

    public String archive(String orderId, String payload) {
        if (!isConfigured()) {
            throw new IllegalStateException("ORDERS_ARCHIVE_BUCKET is not set");
        }
        String key = "orders/" + orderId + "-" + Instant.now().toEpochMilli() + ".json";
        s3.putObject(
                PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .contentType("application/json")
                        .build(),
                RequestBody.fromString(payload));
        return "s3://" + bucket + "/" + key;
    }
}
