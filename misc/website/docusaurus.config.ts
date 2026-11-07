import fs from 'fs';
import path from 'path';
import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'APEX Skills',
  tagline: 'Agent skills for Amazon EKS and Amazon ECS: design, build, assess, upgrade and secure from your coding agent',
  favicon: 'img/favicon.svg',

  url: 'https://aws-samples.github.io',
  baseUrl: '/sample-apex-skills/',
  trailingSlash: true,

  organizationName: 'aws-samples',
  projectName: 'sample-apex-skills',

  onBrokenLinks: 'warn',

  markdown: {
    format: 'detect',
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
    // Docusaurus treats README.md as a directory-index doc, so a generated
    // README.md wrapper sitting next to an index.md (e.g. the
    // eks-cost-intelligence contributor README next to its SKILL.md wrapper)
    // would claim the same route ("Duplicate routes found!") and make
    // plugin-client-redirects emit the same redirect twice. Give such
    // READMEs an explicit non-index slug instead of dropping the page.
    parseFrontMatter: async (params) => {
      const result = await params.defaultParseFrontMatter(params);
      const docsRoot = path.join(__dirname, 'docs');
      const relPath = path.relative(docsRoot, params.filePath).split(path.sep).join('/');
      const match = !relPath.startsWith('..') && relPath.match(/^(.+)\/README\.md$/);
      if (
        match &&
        !result.frontMatter.slug &&
        fs.existsSync(path.join(path.dirname(params.filePath), 'index.md'))
      ) {
        result.frontMatter.slug = `/${match[1]}/README`;
      }
      return result;
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
            description: 'Open-source agent skills for Amazon EKS and Amazon ECS platform engineering, delivered through any coding agent.',
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
            runtimePlatform: 'Claude Code, Kiro CLI, AWS DevOps Agent',
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
          // Every docs page shows this one sidebar; pages (home, /skills,
          // evals) have no docs sidebar, and the blog has its own posts list.
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/aws-samples/sample-apex-skills/edit/main/misc/website/',
          showLastUpdateTime: true,
        },
        blog: {
          path: 'blog',
          routeBasePath: 'blog',
          blogTitle: 'APEX Skills Blog',
          blogDescription: 'Design notes and thought processes behind the APEX skills: how we design skills, the decisions we made and why.',
          blogSidebarTitle: 'Recent posts',
          showReadingTime: true,
          editUrl: 'https://github.com/aws-samples/sample-apex-skills/edit/main/misc/website/',
          onInlineAuthors: 'throw',
          onInlineTags: 'throw',
          onUntruncatedBlogPosts: 'warn',
          feedOptions: {
            type: ['rss', 'atom'],
            title: 'APEX Skills Blog',
            description: 'Design notes and thought processes behind the APEX skills.',
            copyright: `Copyright ${new Date().getFullYear()} Amazon.com, Inc. or its affiliates.`,
          },
        },
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

  plugins: [
    [
      '@docusaurus/plugin-client-redirects',
      {
        createRedirects(existingPath) {
          // Redirect old flat skill paths to new grouped paths
          const groupedMatch = existingPath.match(/^\/docs\/skills\/(eks|ecs|general)\/(.+)/);
          if (groupedMatch) {
            const skillName = groupedMatch[2].replace(/\/$/, '');
            return [`/docs/skills/${skillName}`];
          }
          return undefined;
        },
      },
    ],
  ],

  themeConfig: {
    metadata: [
      {property: 'og:image', content: 'https://aws-samples.github.io/sample-apex-skills/img/og-image.png'},
      {name: 'twitter:image', content: 'https://aws-samples.github.io/sample-apex-skills/img/og-image.png'},
      {property: 'og:image:alt', content: 'APEX Skills title beside an orange diamond mark on a dark navy background, with the tagline Curated AI skills for AWS platform engineering and badges for Agent Skills, MIT-0 and Open Source'},
      {property: 'og:image:width', content: '1200'},
      {property: 'og:image:height', content: '630'},
      {name: 'twitter:image:alt', content: 'APEX Skills title beside an orange diamond mark on a dark navy background, with the tagline Curated AI skills for AWS platform engineering and badges for Agent Skills, MIT-0 and Open Source'},
      {name: 'twitter:card', content: 'summary_large_image'},
    ],
    docs: {
      sidebar: {
        autoCollapseCategories: true,
      },
    },
    navbar: {
      title: 'APEX Skills',
      logo: {
        alt: 'APEX',
        src: 'img/logo.svg',
      },
      items: [
        {
          to: '/docs/getting-started',
          position: 'left',
          label: 'Get started',
        },
        {
          // "Skills" alone is the docs sidebar's table at /docs/skills/;
          // this is the finder, named as in the footer.
          to: '/skills',
          position: 'left',
          label: 'Find a skill',
        },
        {
          to: '/docs/examples',
          position: 'left',
          label: 'Examples',
        },
        {
          to: '/blog',
          position: 'left',
          label: 'Blog',
        },
        {
          to: '/docs/workshop',
          position: 'left',
          label: 'Workshop',
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
            {label: 'Find a skill', to: '/skills'},
            {label: 'Getting started', to: '/docs/getting-started'},
            {label: 'Introduction', to: '/docs/intro'},
            {label: 'Examples', to: '/docs/examples'},
            {label: 'Workshop', to: '/docs/workshop'},
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
            {label: 'Blog', to: '/blog'},
          ],
        },
      ],
      copyright: `Built by AWS Solutions Architects, TAMs and ProServe. Open source under MIT-0; vendored skills keep their own licence. Copyright © ${new Date().getFullYear()} Amazon.com, Inc. or its affiliates.`,
    },
    prism: {
      theme: prismThemes.vsLight,
      // Dracula's comment colour (#6272a4) is 3.0:1 on its background; #9aa5ce is 5.9:1.
      darkTheme: {
        ...prismThemes.dracula,
        styles: prismThemes.dracula.styles.map((s) =>
          s.types.includes('comment') ? {...s, style: {...s.style, color: '#9aa5ce'}} : s,
        ),
      },
      additionalLanguages: ['bash', 'hcl', 'yaml', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
