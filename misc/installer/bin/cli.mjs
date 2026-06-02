#!/usr/bin/env node
import { existsSync, mkdirSync, readdirSync, symlinkSync, readlinkSync, unlinkSync, rmSync, statSync } from 'fs';
import { join, resolve } from 'path';
import { homedir, platform } from 'os';
import { execSync } from 'child_process';
import { createInterface } from 'readline';

const VERSION = '1.0.0';
const REPO_URL = 'https://github.com/aws-samples/sample-apex-skills.git';
const HOME = homedir();
const INSTALL_DIR = join(HOME, '.apex-skills');

// ANSI colors
const c = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  red: '\x1b[31m',
  cyan: '\x1b[36m',
};

const log = (msg) => console.log(msg);
const info = (msg) => log(`${c.blue}i${c.reset} ${msg}`);
const success = (msg) => log(`${c.green}✓${c.reset} ${msg}`);
const warn = (msg) => log(`${c.yellow}!${c.reset} ${msg}`);
const error = (msg) => log(`${c.red}✗${c.reset} ${msg}`);

function banner() {
  log(`\n${c.bold}${c.cyan}  APEX Skills Installer${c.reset} ${c.dim}v${VERSION}${c.reset}`);
  log(`${c.dim}  Platform engineering skills for AI agents${c.reset}\n`);
}

function parseArgs() {
  const args = process.argv.slice(2);
  return {
    claudeOnly: args.includes('--claude-only'),
    kiroOnly: args.includes('--kiro-only'),
    project: args.includes('--project'),
    noSteering: args.includes('--no-steering'),
    update: args.includes('--update'),
    uninstall: args.includes('--uninstall'),
    help: args.includes('--help') || args.includes('-h'),
  };
}

function ask(question, defaultVal = '') {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const suffix = defaultVal ? ` [${defaultVal}]` : '';
  return new Promise((res) => {
    rl.question(`${c.cyan}?${c.reset} ${question}${suffix}: `, (answer) => {
      rl.close();
      res(answer.trim() || defaultVal);
    });
  });
}

function hasGit() {
  try {
    execSync('git --version', { stdio: 'pipe' });
    return true;
  } catch { return false; }
}

function cloneOrUpdate() {
  if (existsSync(INSTALL_DIR)) {
    info('Updating existing installation...');
    try {
      execSync('git pull --ff-only', { cwd: INSTALL_DIR, stdio: 'pipe' });
      success('Updated to latest version');
    } catch (e) {
      warn('Git pull failed — try removing ~/.apex-skills and re-running');
      throw e;
    }
  } else {
    info('Cloning APEX skills repository...');
    try {
      execSync(`git clone --depth 1 ${REPO_URL} "${INSTALL_DIR}"`, { stdio: 'pipe' });
      success('Repository cloned');
    } catch (e) {
      error('Failed to clone repository. Check your internet connection and git access.');
      throw e;
    }
  }
}

function getSkills() {
  const skillsDir = join(INSTALL_DIR, 'skills');
  if (!existsSync(skillsDir)) return [];
  return readdirSync(skillsDir).filter((name) => {
    if (name === 'README.md' || name.startsWith('.')) return false;
    const full = join(skillsDir, name);
    try { return statSync(full).isDirectory(); } catch { return false; }
  });
}

function ensureDir(dir) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

function safeSymlink(target, linkPath) {
  if (existsSync(linkPath)) {
    try {
      const current = readlinkSync(linkPath);
      if (resolve(current) === resolve(target)) return 'skip';
    } catch { /* not a symlink */ }
    unlinkSync(linkPath);
  }
  symlinkSync(target, linkPath);
  return 'created';
}

function symlinkSkills(targetDir, skills) {
  ensureDir(targetDir);
  let count = 0;
  for (const name of skills) {
    const target = join(INSTALL_DIR, 'skills', name);
    const link = join(targetDir, name);
    const result = safeSymlink(target, link);
    if (result === 'created') count++;
  }
  return count;
}

function symlinkSteeringClaude(commandsDir) {
  const source = join(INSTALL_DIR, 'steering', 'commands', 'apex');
  if (!existsSync(source)) { warn('No steering commands found in repo'); return; }
  ensureDir(join(commandsDir));
  const link = join(commandsDir, 'apex');
  safeSymlink(source, link);
  success(`Steering commands linked to ${c.dim}${link}${c.reset}`);
}

function symlinkSteeringKiro(steeringDir) {
  const source = join(INSTALL_DIR, 'steering', 'workflows');
  if (!existsSync(source)) { warn('No steering workflows found in repo'); return; }
  ensureDir(steeringDir);
  const files = readdirSync(source).filter((f) => f.endsWith('.md'));
  for (const file of files) {
    safeSymlink(join(source, file), join(steeringDir, file));
  }
  success(`Steering workflows linked to ${c.dim}${steeringDir}${c.reset} (${files.length} files)`);
}

function uninstall(flags) {
  banner();
  info('Uninstalling APEX skills...');
  const dirs = [];
  if (!flags.kiroOnly) dirs.push(join(HOME, '.claude', 'skills'));
  if (!flags.claudeOnly) dirs.push(join(HOME, '.kiro', 'skills'));

  let removed = 0;
  for (const dir of dirs) {
    if (!existsSync(dir)) continue;
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      try {
        const target = readlinkSync(full);
        if (resolve(target).startsWith(resolve(INSTALL_DIR))) {
          unlinkSync(full);
          removed++;
        }
      } catch { /* not a symlink or can't read */ }
    }
  }

  // Remove steering symlinks
  const claudeCmd = join(HOME, '.claude', 'commands', 'apex');
  if (existsSync(claudeCmd)) { try { unlinkSync(claudeCmd); removed++; } catch {} }

  const kiroSteering = join(HOME, '.kiro', 'steering');
  if (existsSync(kiroSteering)) {
    for (const f of readdirSync(kiroSteering)) {
      const full = join(kiroSteering, f);
      try {
        const target = readlinkSync(full);
        if (resolve(target).startsWith(resolve(INSTALL_DIR))) { unlinkSync(full); removed++; }
      } catch {}
    }
  }

  success(`Removed ${removed} symlinks`);

  if (existsSync(INSTALL_DIR)) {
    info(`Repository still at ${INSTALL_DIR}`);
    info('Remove it manually with: rm -rf ~/.apex-skills');
  }
  log('');
}

function showHelp() {
  banner();
  log(`${c.bold}Usage:${c.reset}  npx apex-skills [flags]\n`);
  log(`${c.bold}Flags:${c.reset}`);
  log(`  --claude-only    Install for Claude Code only`);
  log(`  --kiro-only      Install for Kiro CLI only`);
  log(`  --project        Install to current project instead of global`);
  log(`  --no-steering    Skip steering/commands setup`);
  log(`  --update         Pull latest and re-symlink (non-interactive)`);
  log(`  --uninstall      Remove symlinks (keeps cloned repo)`);
  log(`  -h, --help       Show this help\n`);
  log(`${c.bold}Examples:${c.reset}`);
  log(`  npx apex-skills                   Interactive install`);
  log(`  npx apex-skills --update          Update to latest skills`);
  log(`  npx apex-skills --claude-only     Install for Claude Code only`);
  log(`  npx apex-skills --project         Install into current project\n`);
}

async function main() {
  const flags = parseArgs();

  if (flags.help) { showHelp(); process.exit(0); }

  if (platform() === 'win32') {
    error('Windows is not supported (symlinks require elevated permissions).');
    error('Use WSL (Windows Subsystem for Linux) instead.');
    process.exit(1);
  }

  if (flags.uninstall) { uninstall(flags); process.exit(0); }

  banner();

  if (!hasGit()) {
    error('git is required but not found in PATH.');
    process.exit(1);
  }

  // Detect targets
  const claudeDir = join(HOME, '.claude');
  const kiroDir = join(HOME, '.kiro');
  let installClaude = !flags.kiroOnly && existsSync(claudeDir);
  let installKiro = !flags.claudeOnly && existsSync(kiroDir);

  if (!installClaude && !installKiro && !flags.claudeOnly && !flags.kiroOnly) {
    warn('Neither ~/.claude nor ~/.kiro found.');
    const choice = await ask('Create directory for (claude/kiro/both)', 'claude');
    if (choice === 'claude' || choice === 'both') { ensureDir(claudeDir); installClaude = true; }
    if (choice === 'kiro' || choice === 'both') { ensureDir(kiroDir); installKiro = true; }
    if (!installClaude && !installKiro) { error('No target selected.'); process.exit(1); }
  }

  if (flags.claudeOnly && !existsSync(claudeDir)) { ensureDir(claudeDir); installClaude = true; }
  if (flags.kiroOnly && !existsSync(kiroDir)) { ensureDir(kiroDir); installKiro = true; }

  // Clone or update
  cloneOrUpdate();

  const skills = getSkills();
  if (skills.length === 0) { error('No skills found in repository.'); process.exit(1); }

  info(`Found ${skills.length} skills`);

  // Determine skill target directories
  let claudeSkillsDir, kiroSkillsDir;
  if (flags.project) {
    const cwd = process.cwd();
    claudeSkillsDir = join(cwd, '.claude', 'skills');
    kiroSkillsDir = join(cwd, '.kiro', 'skills');
  } else {
    claudeSkillsDir = join(claudeDir, 'skills');
    kiroSkillsDir = join(kiroDir, 'skills');
  }

  // Install skills
  if (installClaude) {
    const count = symlinkSkills(claudeSkillsDir, skills);
    success(`Installed ${skills.length} skills to ${c.dim}${claudeSkillsDir}${c.reset}${count > 0 ? ` (${count} new)` : ''}`);
  }
  if (installKiro) {
    const count = symlinkSkills(kiroSkillsDir, skills);
    success(`Installed ${skills.length} skills to ${c.dim}${kiroSkillsDir}${c.reset}${count > 0 ? ` (${count} new)` : ''}`);
  }

  // Steering
  let doSteering = !flags.noSteering;
  if (doSteering && !flags.update) {
    if (!flags.noSteering && !flags.claudeOnly && !flags.kiroOnly && !flags.update) {
      const answer = await ask('Install steering workflows/commands? (y/n)', 'y');
      doSteering = answer.toLowerCase() === 'y' || answer.toLowerCase() === 'yes';
    }
  }

  if (doSteering) {
    if (installClaude) {
      const cmdDir = flags.project ? join(process.cwd(), '.claude', 'commands') : join(claudeDir, 'commands');
      symlinkSteeringClaude(cmdDir);
    }
    if (installKiro) {
      const stDir = flags.project ? join(process.cwd(), '.kiro', 'steering') : join(kiroDir, 'steering');
      symlinkSteeringKiro(stDir);
    }
  }

  // Summary
  log('');
  log(`${c.bold}${c.green}Done!${c.reset}\n`);
  log(`${c.dim}  Skills: ${skills.join(', ')}${c.reset}\n`);
  if (installClaude) log(`  ${c.bold}Claude Code:${c.reset} ask your agent about EKS best practices`);
  if (installKiro) log(`  ${c.bold}Kiro CLI:${c.reset} use /apex commands for guided workflows`);
  log(`\n  Update anytime: ${c.cyan}npx apex-skills --update${c.reset}`);
  log('');
}

main().catch((e) => {
  error(e.message || 'Unexpected error');
  process.exit(1);
});
