# Article Platform: API 200, frontend 404

After migrating a Vite frontend to Next.js, the backend /locations endpoint returns HTTP 200, but the corresponding frontend page displays HTTP 404.

Stack: Next.js, Fastify, Prisma, PostgreSQL, TypeScript.
Evidence available here: user-reported symptom only. No repository files, exact payload, route tree or logs were supplied to this implementation.
Investigate frontend routing, API base URLs, route mismatches, response contracts, server/client boundaries and data expectations. Do not choose the root cause in advance.
Constraints: reproduce first, preserve the existing map design, avoid destructive DB changes, propose the smallest verified fix and regression checks.
