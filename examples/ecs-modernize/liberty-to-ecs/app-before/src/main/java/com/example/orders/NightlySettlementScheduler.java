package com.example.orders;

import java.util.Date;
import java.util.logging.Logger;

import commonj.timers.Timer;
import commonj.timers.TimerListener;
import commonj.timers.TimerManager;

import javax.annotation.Resource;
import javax.servlet.ServletContextEvent;
import javax.servlet.ServletContextListener;
import javax.servlet.annotation.WebListener;

/**
 * Runs nightly settlement.
 *
 * PLANTED BLOCKERS (os_host_dependency — code-level app-server coupling):
 *
 *   Uses the CommonJ TimerManager / WorkManager programming model
 *   (commonj.timers.*), a WebSphere-specific asynchronous-beans surface. This
 *   is code-level coupling, not descriptor-level: the dependence lives in
 *   application logic and travels with the code wherever it goes. It must be
 *   replaced with EE Concurrency (ManagedScheduledExecutorService) before the
 *   app can leave the WebSphere family.
 *
 *   See the skill's tWAS -> Liberty proprietary API replacement map:
 *   skills/ecs-modernize/references/code-transformation-agent-led.md
 *
 * NOTE: this class does not compile against a plain Java EE 7 API jar — the
 * commonj.* packages ship with WebSphere. That is deliberate and is exactly
 * what the assessment reports as vendor lock-in. It is excluded from the
 * compile check in scripts/build.sh; see that script's comments.
 */
@WebListener
public class NightlySettlementScheduler implements ServletContextListener {

    private static final Logger LOG =
            Logger.getLogger(NightlySettlementScheduler.class.getName());

    /** PLANTED: WebSphere-specific TimerManager pulled from the WAS JNDI namespace. */
    @Resource(lookup = "wm/default")
    private TimerManager timerManager;

    @Override
    public void contextInitialized(ServletContextEvent sce) {
        // PLANTED: proprietary scheduling API rather than @Schedule / EE Concurrency
        timerManager.schedule(new TimerListener() {
            @Override
            public void timerExpired(Timer timer) {
                LOG.info("settlement run at " + new Date());
            }
        }, 60_000L, 86_400_000L);
    }

    @Override
    public void contextDestroyed(ServletContextEvent sce) {
        if (timerManager != null) {
            timerManager.stop();
        }
    }
}
