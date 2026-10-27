"""Independent checks of actual agent report outputs for the #250 smoke test."""

from datetime import datetime
import hashlib
from pathlib import Path
import re

import yaml


def inventory(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(root).rglob('*') if p.is_file()}


def check_outputs(root, before, *, cluster, started, ended, prefix=None,
                  collision=False):
    """Return violations; timestamps use the subject's recorded local timezone.

    Non-Markdown/YAML scratch files are allowed. One new report pair is required on
    success; collision runs must preserve all existing files and add no reports.
    """
    root = Path(root)
    after = inventory(root)
    errors = [f'Preexisting file changed or disappeared: {name}'
              for name, digest in before.items() if after.get(name) != digest]
    new_reports = sorted(name for name in after.keys() - before.keys()
                         if Path(name).suffix in ('.md', '.yaml'))
    if collision:
        if prefix is None or not any(prefix + suffix in before for suffix in ('.md', '.yaml')):
            errors.append('Collision requires an explicit prefix with a preexisting destination')
        if new_reports:
            errors.append(f'Collision produced unexpected reports: {new_reports}')
        return errors
    markdown = [name for name in new_reports if name.endswith('.md')]
    machine = [name for name in new_reports if name.endswith('.yaml')]
    if len(markdown) != 1 or len(machine) != 1:
        return errors + [f'Expected one new report pair; found {new_reports}']
    md, yml = markdown[0], machine[0]
    if md[:-3] != yml[:-5]:
        errors.append('Markdown and YAML basenames differ')
    if prefix is not None:
        if md != prefix + '.md' or yml != prefix + '.yaml':
            errors.append(f'Explicit prefix was not honored: {md}, {yml}')
    else:
        match = re.fullmatch(r'EKS-Recon-' + re.escape(cluster)
                             + r'-(\d{4}-\d{2}-\d{2}-\d{4})\.md', md)
        if not match:
            errors.append(f'Invalid default filename: {md}')
        else:
            try:
                stamp = datetime.strptime(match[1], '%Y-%m-%d-%H%M').replace(tzinfo=started.tzinfo)
                if not started.replace(second=0, microsecond=0) <= stamp <= ended:
                    errors.append('Filename timestamp is outside the agent run')
            except ValueError:
                errors.append('Filename timestamp is not a valid date/time')
    text = (root / md).read_text(encoding='utf-8')
    section = re.search(r'^## Machine artifact\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not section or not re.search(r'`' + re.escape(yml) + r'`', section[1]):
        errors.append('Machine artifact section does not name the actual YAML path')
    try:
        data = yaml.safe_load((root / yml).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('cluster'), dict) or data['cluster'].get('name') != cluster:
            errors.append('YAML cluster.name does not match the target')
    except yaml.YAMLError:
        errors.append('Report YAML is invalid')
    return errors
