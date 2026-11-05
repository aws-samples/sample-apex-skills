import React, {useState, useCallback, useEffect, useRef} from 'react';

function toRawUrl(editUrl: string): string | null {
  // Match /blob/branch/path or /edit/branch/path
  const match = editUrl.match(
    /^https:\/\/github\.com\/([^/]+)\/([^/]+)\/(blob|edit)\/([^/]+)\/(.+)$/
  );
  if (!match) return null;
  const [, owner, repo, , branch, path] = match;
  return `https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${path}`;
}

interface Props {
  editUrl: string;
}

// "Copy page" plus a menu: copy as markdown, view the .md source, or open
// the page in Claude with a prompt that points at the .md source.
export default function CopyMarkdownButton({editUrl}: Props): React.JSX.Element | null {
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const rawUrl = toRawUrl(editUrl);

  const handleCopy = useCallback(async () => {
    if (!rawUrl) return;
    setOpen(false);
    try {
      const res = await fetch(rawUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.open(rawUrl, '_blank');
    }
  }, [rawUrl]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !menuRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  if (!rawUrl) return null;

  const claudeUrl = `https://claude.ai/new?q=${encodeURIComponent(
    `Read ${rawUrl} so I can ask questions about it.`,
  )}`;

  return (
    <div className="copy-page-menu" ref={menuRef}>
      <button
        type="button"
        className="copy-page-button"
        onClick={handleCopy}
        title="Copy source markdown to clipboard"
        aria-label="Copy page"
      >
        {copied ? (
          <>
            <svg className="copy-page-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3.5 8.5 6.5 11.5 12.5 5.5" />
            </svg>
            <span>Copied!</span>
          </>
        ) : (
          <>
            <svg className="copy-page-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="5.5" y="5.5" width="7" height="8" rx="1" />
              <path d="M3.5 10.5v-7a1 1 0 0 1 1-1h7" />
            </svg>
            <span>Copy page</span>
          </>
        )}
      </button>
      <button
        type="button"
        className="copy-page-button copy-page-toggle"
        aria-expanded={open}
        aria-label="More page actions"
        onClick={() => setOpen(!open)}
      >
        <svg className="copy-page-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 6 8 10 12 6" />
        </svg>
      </button>
      {open && (
        <ul className="copy-page-list">
          <li>
            <button type="button" onClick={handleCopy}>
              Copy as markdown
            </button>
          </li>
          <li>
            <a href={rawUrl} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
              View .md
            </a>
          </li>
          <li>
            <a href={claudeUrl} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
              Open in Claude
            </a>
          </li>
        </ul>
      )}
    </div>
  );
}
