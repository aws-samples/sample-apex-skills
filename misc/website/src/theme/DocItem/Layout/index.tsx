import React from 'react';
import Layout from '@theme-original/DocItem/Layout';
import type LayoutType from '@theme/DocItem/Layout';
import type {WrapperProps} from '@docusaurus/types';
import CopyMarkdownButton from '@site/src/components/CopyMarkdownButton';
import {useDoc} from '@docusaurus/plugin-content-docs/client';

type Props = WrapperProps<typeof LayoutType>;

export default function LayoutWrapper(props: Props): React.JSX.Element {
  const {metadata} = useDoc();
  const editUrl = metadata.editUrl;

  return (
    <>
      {editUrl && (
        <div className="copy-page-row">
          <CopyMarkdownButton editUrl={editUrl} />
        </div>
      )}
      <Layout {...props} />
    </>
  );
}
