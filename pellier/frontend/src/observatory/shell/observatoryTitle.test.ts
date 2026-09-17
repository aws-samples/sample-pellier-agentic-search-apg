import { observatoryTitleForPath } from './ObservatoryFrame';

describe('observatoryTitleForPath', () => {
  it('names the Lab Collection at the surface root', () => {
    expect(observatoryTitleForPath('/observatory')).toBe(
      'Lab Collection · Pellier Observatory',
    );
  });

  it('names nested routes by their surface', () => {
    expect(observatoryTitleForPath('/observatory/proof-board')).toBe(
      'Proof Board · Pellier Observatory',
    );
    expect(observatoryTitleForPath('/observatory/sessions/abc/chat')).toBe(
      'Sessions · Pellier Observatory',
    );
    expect(observatoryTitleForPath('/observatory/labs/grounded-inventory')).toBe(
      'Lab 1: Build a PostgreSQL-Grounded Agent · Pellier Observatory',
    );
  });
});
