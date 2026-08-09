# PrismOS Frontend

A minimalistic and easy-to-use web interface with a modern and flexible architecture.

## Tech Stack

- **Framework**: [Next.js 16](https://nextjs.org/) with [App Router](https://nextjs.org/docs/app)
- **UI**: [React 19](https://react.dev/), [Tailwind CSS 4](https://tailwindcss.com/), [Shadcn UI](https://ui.shadcn.com/), [MagicUI](https://magicui.design/) and [React Bits](https://reactbits.dev/)
- **AI Integration**: [LangGraph SDK](https://www.npmjs.com/package/@langchain/langgraph-sdk) and [Vercel AI Elements](https://vercel.com/ai-sdk/ai-elements)

## Quick Start

### Prerequisites

- Node.js 22+
- pnpm 10.26.2+

### Installation

```bash
# Install dependencies
pnpm install

# Copy environment variables
cp .env.example .env
# Edit .env with your configuration
```

### Development

```bash
# Start development server
pnpm dev

# The app will be available at http://localhost:3000
```

### Build

```bash
# Type check
pnpm typecheck

# Lint
pnpm lint

# Build for production
pnpm build

# Start production server
pnpm start
```

## Site Map

```
├── /                              # Landing page
├── /sign-in                       # Sign in
├── /sign-up                       # Sign up
├── /change-password               # Password change
├── /select-workspace              # Workspace selection
├── /workspace                     # Main workspace
│   ├── /workspace/overview        # Overview dashboard
│   ├── /workspace/chats           # Chat list
│   ├── /workspace/chats/[id]      # Specific chat
│   ├── /workspace/agents          # Custom agents list
│   ├── /workspace/agents/new      # Create new agent
│   ├── /workspace/agents/[name]/chats/[id]  # Agent chat
│   └── /workspace/announcements   # Announcements
├── /admin                         # Platform admin
│   ├── /admin/users               # User management
│   ├── /admin/tenants             # Tenant management
│   ├── /admin/models              # Model templates
│   ├── /admin/tools               # Tool management
│   ├── /admin/audit               # Audit log
│   ├── /admin/security            # Security settings
│   └── /admin/announcements       # Platform announcements
└── /tenant-admin                  # Tenant admin
    ├── /tenant-admin/members      # Member management
    ├── /tenant-admin/models       # Tenant models
    ├── /tenant-admin/skills       # Skill management
    ├── /tenant-admin/tools        # Tool management
    ├── /tenant-admin/audit        # Tenant audit log
    └── /tenant-admin/settings     # Tenant settings
```

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Backend API URLs (optional, uses nginx proxy by default)
NEXT_PUBLIC_BACKEND_BASE_URL="http://localhost:8001"
# LangGraph API URLs (optional, uses nginx proxy by default)
NEXT_PUBLIC_LANGGRAPH_BASE_URL="http://localhost:2024"
```

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── api/                # API routes
│   ├── workspace/          # Main workspace pages
│   └── mock/               # Mock/demo pages
├── components/             # React components
│   ├── ui/                 # Reusable UI components
│   ├── workspace/          # Workspace-specific components
│   ├── landing/            # Landing page components
│   └── ai-elements/        # AI-related UI elements
├── core/                   # Core business logic
│   ├── api/                # API client & data fetching
│   ├── artifacts/          # Artifact management
│   ├── config/              # App configuration
│   ├── i18n/               # Internationalization
│   ├── mcp/                # MCP integration
│   ├── messages/           # Message handling
│   ├── models/             # Data models & types
│   ├── settings/           # User settings
│   ├── skills/             # Skills system
│   ├── threads/            # Thread management
│   ├── todos/              # Todo system
│   └── utils/              # Utility functions
├── hooks/                  # Custom React hooks
├── lib/                    # Shared libraries & utilities
├── server/                 # Server-side code
│   └── better-auth/        # Authentication setup
└── styles/                 # Global styles
```

## Scripts

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start development server with Turbopack |
| `pnpm build` | Build for production |
| `pnpm start` | Start production server |
| `pnpm lint` | Run ESLint |
| `pnpm lint:fix` | Fix ESLint issues |
| `pnpm typecheck` | Run TypeScript type checking |
| `pnpm check` | Run both lint and typecheck |

## Development Notes

- Uses pnpm workspaces (see `packageManager` in package.json)
- Turbopack enabled by default in development for faster builds
- Environment validation can be skipped with `SKIP_ENV_VALIDATION=1` (useful for Docker)
- Backend API URLs are optional; nginx proxy is used by default in development

## License

MIT License. See [LICENSE](../LICENSE) for details.
