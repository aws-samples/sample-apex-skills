package com.example.orders;

import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.Resource;
import jakarta.ejb.Singleton;
import jakarta.ejb.Startup;
import jakarta.enterprise.concurrent.ManagedScheduledExecutorService;

/**
 * REARCHITECTED settlement scheduler.
 *
 * Fixes, versus app-before:
 *
 *  * os_host_dependency — the WebSphere-specific CommonJ TimerManager
 *    (commonj.timers.*) is replaced with the Jakarta EE Concurrency standard
 *    ManagedScheduledExecutorService. This is the replacement the skill's tWAS
 *    -> Liberty proprietary API map prescribes for CommonJ WorkManager /
 *    TimerManager. The code no longer depends on any vendor server API, so it
 *    compiles and runs on any Jakarta EE 10 runtime — no compiler exclusion
 *    needed (contrast app-before/pom.xml).
 *
 * NOTE on the host cron job that app-before relied on: the settlement schedule
 * that lived in /etc/cron.d on the VM is a separate decision point. Keeping it
 * in-process (as here) is one option; the alternative the skill raises is an
 * ECS scheduled task. This exercise keeps it in-process to stay
 * self-contained.
 */
@Startup
@Singleton
public class NightlySettlementScheduler {

    private static final Logger LOG =
            Logger.getLogger(NightlySettlementScheduler.class.getName());

    @Resource
    private ManagedScheduledExecutorService scheduler;

    @PostConstruct
    public void start() {
        scheduler.scheduleAtFixedRate(
                () -> LOG.info("settlement run"),
                1, 24 * 60, TimeUnit.MINUTES);
    }
}
