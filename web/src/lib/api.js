// Shared fetch helpers: do the request, parse JSON, and on failure throw an
// Error carrying the server's `detail` (the `res.json().catch(()=>({})).detail`
// pattern that used to be copy-pasted into every call site).

async function httpError(res) {
  const body = await res.json().catch(() => ({}))
  const err = new Error(
    typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`,
  )
  err.status = res.status
  err.detail = body.detail // may be a string or a structured object
  err.body = body
  return err
}

export async function getJSON(url) {
  const res = await fetch(url)
  if (!res.ok) throw await httpError(res)
  return res.json()
}

export async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok) throw await httpError(res)
  return res.json()
}
