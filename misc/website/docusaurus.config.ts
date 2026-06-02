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

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/aws-samples/sample-apex-skills/edit/main/misc/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
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
