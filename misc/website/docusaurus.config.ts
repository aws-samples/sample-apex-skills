import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'APEX Skills',
  tagline: 'Platform engineering with agents — curated AWS skills delivered through your AI coding agent',
  favicon: 'img/favicon.svg',

  url: 'https://aws-samples.github.io',
  baseUrl: '/sample-apex-skills/',

  organizationName: 'aws-samples',
  projectName: 'sample-apex-skills',

  onBrokenLinks: 'warn',

  markdown: {
    format: 'detect',
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  headTags: [
    {
      tagName: 'script',
      attributes: {type: 'application/ld+json'},
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': 'WebSite',
            name: 'APEX Skills',
            url: 'https://aws-samples.github.io/sample-apex-skills/',
            description: 'Curated agentic AI skills for AWS platform engineering, delivered through any coding agent.',
          },
          {
            '@type': 'Organization',
            name: 'AWS Samples',
            url: 'https://github.com/aws-samples',
          },
          {
            '@type': 'SoftwareSourceCode',
            name: 'sample-apex-skills',
            codeRepository: 'https://github.com/aws-samples/sample-apex-skills',
            programmingLanguage: ['TypeScript', 'Python', 'Bash', 'HCL'],
            license: 'https://opensource.org/licenses/MIT-0',
            runtimePlatform: 'Claude Code, Kiro CLI',
          },
        ],
      }),
    },
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/aws-samples/sample-apex-skills/edit/main/misc/website/',
          showLastUpdateTime: true,
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
        sitemap: {
          lastmod: 'date',
          changefreq: null,
          priority: null,
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    metadata: [
      {property: 'og:image', content: 'https://aws-samples.github.io/sample-apex-skills/img/og-image.svg'},
      {name: 'twitter:image', content: 'https://aws-samples.github.io/sample-apex-skills/img/og-image.svg'},
      {name: 'twitter:card', content: 'summary_large_image'},
      {name: 'keywords', content: 'AWS, EKS, platform engineering, AI agent skills, Claude Code, Kiro CLI, Kubernetes, infrastructure as code, agentic AI, DevOps automation'},
    ],
    navbar: {
      title: 'APEX Skills',
      logo: {
        alt: 'APEX',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'doc',
          docId: 'intro',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/docs/skills',
          position: 'left',
          label: 'Skills',
        },
        {
          to: '/docs/steering',
          position: 'left',
          label: 'Steering',
        },
        {
          to: '/docs/examples',
          position: 'left',
          label: 'Examples',
        },
        {
          to: '/docs/contributing',
          position: 'left',
          label: 'Contributing',
        },
        {
          href: 'https://github.com/aws-samples/sample-apex-skills',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Introduction', to: '/docs/intro'},
            {label: 'Getting Started', to: '/docs/getting-started'},
            {label: 'Skills', to: '/docs/skills'},
            {label: 'Steering', to: '/docs/steering'},
          ],
        },
        {
          title: 'Community',
          items: [
            {label: 'Agent Skills standard', href: 'https://agentskills.io/'},
            {label: 'AWS Samples', href: 'https://github.com/aws-samples'},
          ],
        },
        {
          title: 'More',
          items: [
            {label: 'GitHub', href: 'https://github.com/aws-samples/sample-apex-skills'},
            {label: 'Contributing', to: '/docs/contributing'},
          ],
        },
      ],
      copyright: `Built by AWS Solutions Architects, TAMs, and ProServe · MIT-0 License · Copyright © ${new Date().getFullYear()} Amazon.com, Inc. or its affiliates.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'hcl', 'yaml', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
