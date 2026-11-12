import { useSegments } from 'expo-router';

/* True on the owner dashboard screens (Home, Requests, Beds, Money, More, Residents, Repairs): the route group
   `(owner)`. On a wide website that area has its own sidebar with the logo, so the site header is not shown there.
   Stack screens opened from it (a resident, an agreement) are outside the group, and do get the header. */
export function useInOwnerDashboard(): boolean {
  return useSegments()[0] === '(owner)';
}
