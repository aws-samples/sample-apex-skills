# OpenRewrite plugin configuration

These are the exact coordinates from the successful lived run (Java 11 to 21, Boot 2.7.18 to 3.3.13). Copy them; do not copy the plugin config already in the target pom, which is very likely stale (see the warning at the bottom).

## Versions

| Artifact | Version |
|----------|---------|
| `org.openrewrite.maven:rewrite-maven-plugin` | 6.46.1 |
| `org.openrewrite.recipe:rewrite-spring` | 6.37.0 |
| `org.openrewrite.recipe:rewrite-migrate-java` | 3.42.0 |
| `org.openrewrite.recipe:rewrite-recipe-bom` | 3.37.0 (pin by value, see note) |
| Active recipes (all three) | `org.openrewrite.java.migrate.UpgradeToJava21`, `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_3`, `org.openrewrite.java.migrate.jakarta.JakartaEE10` |

Run **all three** recipes together. This corrects a tempting shortcut: `UpgradeSpringBoot_3_3` alone does **not** reach Java 21. The Boot recipe transitively includes both `UpgradeToJava17` (Boot 3's Java floor) and `JakartaEE10` (via `UpgradeSpringFramework_6_0`), so alone it lands the project at Java 17 with the `javax` to `jakarta` migration already applied. It does not include `UpgradeToJava21` (that recipe is nowhere in the Boot chain). So the one genuinely-required explicit add is `org.openrewrite.java.migrate.UpgradeToJava21`. `JakartaEE10` is listed explicitly only as a redundant-but-harmless (idempotent) entry for clarity and robustness (kit poms list all three for the same reason); the Boot chain already runs it. `rewrite-migrate-java` supplies `UpgradeToJava21` and `JakartaEE10`; `rewrite-spring` supplies `UpgradeSpringBoot_3_3`.

## Plugin block

Put this in the parent pom `<build><plugins>`. Note the recipe artifacts go in the plugin's own `<dependencies>`, and they are pinned by value.

```xml
<plugin>
  <groupId>org.openrewrite.maven</groupId>
  <artifactId>rewrite-maven-plugin</artifactId>
  <version>6.46.1</version>
  <configuration>
    <activeRecipes>
      <recipe>org.openrewrite.java.migrate.UpgradeToJava21</recipe>
      <recipe>org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_3</recipe>
      <recipe>org.openrewrite.java.migrate.jakarta.JakartaEE10</recipe>
    </activeRecipes>
  </configuration>
  <dependencies>
    <dependency>
      <groupId>org.openrewrite.recipe</groupId>
      <artifactId>rewrite-spring</artifactId>
      <version>6.37.0</version>
    </dependency>
    <dependency>
      <groupId>org.openrewrite.recipe</groupId>
      <artifactId>rewrite-migrate-java</artifactId>
      <version>3.42.0</version>
    </dependency>
  </dependencies>
</plugin>
```

### Why the recipe-bom is pinned by value

The tidy way to align recipe versions is normally to import `org.openrewrite.recipe:rewrite-recipe-bom` with `<scope>import</scope>` in `dependencyManagement`. That does not work here: an import-scoped BOM is only legal in `<dependencyManagement>`, not inside a plugin's `<dependencies>` block, which is where the recipe artifacts have to live. So you pin `rewrite-spring` and `rewrite-migrate-java` to the versions that the 3.37.0 recipe-bom would have selected, directly. If you later move the recipe deps out to `dependencyManagement`, you can import the BOM instead; inside the plugin, pin by value.

## Invocation

```bash
mvn -q test                                                        # baseline, old JDK, must be green
mvn -U org.openrewrite.maven:rewrite-maven-plugin:dryRun           # preview the diff
mvn org.openrewrite.maven:rewrite-maven-plugin:run                 # apply
mvn -q test                                                        # re-test on target JDK
javap -v -cp <module>/target/classes <AnyClass> | grep 'major version'  # expect: major version: 65 (Java 21)
```

The `-U` on the dry run forces a check for the plugin and recipe artifacts so you are not running against a stale local cache.

Do not stop at a green `mvn test`. Assert the bytecode is Java 21: class-file **major version 65**. Major version 61 means the recipe only floored you at Java 17, so `UpgradeToJava21` was not active. Cross-check that the parent pom now sets `<java.version>21</java.version>`.

## Version-drift warning (verified)

Poms in the field pin an older stack, and superseded run notes circulate with different values. Concretely, the reference app's own pom pinned plugin **5.46.0**, rewrite-spring **5.24.1**, rewrite-migrate-java **2.29.1**, and staged (commented-out) recipes `UpgradeToJava21` / `UpgradeSpringBoot_3_x` / `JakartaEE10`. Superseded transform notes show tcnative **2.0.69** and Boot **3.2.12** with recipe `_3_2`.

None of those are the values that produced a green build. Use 6.46.1 / 6.37.0 / 3.42.0 / `UpgradeSpringBoot_3_3` / Boot 3.3.x. When you open the target pom, replace the stale plugin config outright rather than editing around it.
