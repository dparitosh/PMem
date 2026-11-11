describe('GraphWorkspace module', () => {
  it('compiles and exports the workspace component', async () => {
    const module = await import('./GraphWorkspace');
    expect(module.default).toBeDefined();
  }, 60000);
});
