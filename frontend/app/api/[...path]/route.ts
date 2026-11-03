import { proxyApiRequest } from '@/lib/api/server-client'

type RouteContext = {
  params: Promise<{ path: string[] }>
}

async function handleRequest(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { path } = await context.params
  return proxyApiRequest(request, path)
}

export const GET = handleRequest
export const POST = handleRequest
export const PUT = handleRequest
export const DELETE = handleRequest
