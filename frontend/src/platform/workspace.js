export const workspaceHome = user => user?.workspace === 'india' ? '/india/dashboard' : '/dashboard';
export function loginDestination(user, requested) {
  const home = workspaceHome(user);
  if (user?.workspace === 'india') return home;
  // Preserve existing dashboard deep links, but never send an existing account into India.
  if (typeof requested === 'string' && /^\/(dashboard(?:\/|[?#]|$)|findings(?:[?#]|$)|predictions(?:[?#]|$)|recommendations(?:[?#]|$))/.test(requested)) return requested;
  return home;
}
