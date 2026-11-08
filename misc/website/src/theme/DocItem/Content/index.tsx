import React from 'react';
import Content from '@theme-original/DocItem/Content';
import type ContentType from '@theme/DocItem/Content';
import type {WrapperProps} from '@docusaurus/types';
import {useDoc} from '@docusaurus/plugin-content-docs/client';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import SkillHeader from '@site/src/components/SkillHeader';

type Props = WrapperProps<typeof ContentType>;

// Skill pages open with a short "at a glance" block from the catalogue; every
// other doc renders as before.
export default function ContentWrapper(props: Props): React.JSX.Element {
  const {metadata} = useDoc();
  const {siteConfig} = useDocusaurusContext();
  return (
    <>
      <SkillHeader permalink={metadata.permalink} baseUrl={siteConfig.baseUrl} />
      <Content {...props} />
    </>
  );
}
