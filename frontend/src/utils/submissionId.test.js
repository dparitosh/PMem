import {createSubmissionId} from './submissionId';

test('uses native UUID generation when supported',()=>{
 const provider={randomUUID:vi.fn(()=> '12345678-1234-4123-8123-123456789abc')};
 expect(createSubmissionId(provider)).toBe('12345678-1234-4123-8123-123456789abc');
 expect(provider.randomUUID).toHaveBeenCalledOnce();
});

test('HTTP-compatible random bytes produce canonical version-4 UUIDs',()=>{
 const getRandomValues=vi.fn(bytes=>{bytes.fill(255);return bytes;});
 const uuid=createSubmissionId({getRandomValues});
 expect(uuid).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');
 expect(uuid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
 expect(getRandomValues.mock.calls[0][0]).toBeInstanceOf(Uint8Array);
});

test('never substitutes a weak random or timestamp identity',()=>{
 const random=vi.spyOn(Math,'random').mockImplementation(()=>{throw new Error('Weak randomness must not be used');});
 try{expect(()=>createSubmissionId({})).toThrow(/safe investigation reference/);}finally{random.mockRestore();}
});
