import React, {useState, useCallback} from 'react';

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

export default function CopyMarkdownButton({editUrl}: Props): React.JSX.Element | null {
  const [copied, setCopied] = useState(false);
  const rawUrl = toRawUrl(editUrl);

  if (!rawUrl) return null;

  const handleCopy = useCallback(async () => {
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

  return (
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
  );
}
