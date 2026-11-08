import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import SkillFinder from '@site/src/components/SkillFinder';
import {skillCount} from '@site/src/components/skillCatalog';

export default function Skills(): ReactNode {
  return (
    <Layout
      title="Find an EKS or ECS skill"
      description={`Search and compare all ${skillCount} APEX skills for Amazon EKS and Amazon ECS: what each one is for, what it is not for and what you get.`}
    >
      <main className="apex-catalog">
        <div className="apex-wrap">
          <h1 className="apex-catalog__title">Find a skill</h1>
          <p className="apex-catalog__intro">
            Search by task, or filter by platform. Each skill says what it is for, what it is not for and what you
            get back.
          </p>
          <SkillFinder variant="page" />
        </div>
      </main>
    </Layout>
  );
}
