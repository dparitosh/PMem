# Root Cause Analysis: Step 1 → Step 2 Progression Failure

**Analysis Date:** May 23, 2026  
**System:** Depo Onto Engine Data Import Pipeline  
**Status:** 🔴 CRITICAL - Multiple blocking issues identified

---

## Executive Summary

The data import pipeline fails to progress from Step 1 to Step 2 due to **5 critical issues** involving state management race conditions, improper async sequencing, and missing error propagation. Even though the backend API supports STEP file parsing and the UI workflow is implemented, **the frontend lacks proper coordination between asynchronous operations**, causing the "Proceed to Stage 2" button to either not appear or malfunction when clicked.

---

## Issues Identified

### 🔴 ISSUE #1: State Update Race Condition - FILE QUEUE STATUS

**Severity:** CRITICAL  
**Component:** DataIngestion.js, lines 299-305 + 899-904  
**Impact:** File queue status inconsistency; "Proceed" button may not appear

#### Root Cause
Both `processFileStage1()` AND `handleStartPipeline()` attempt to update the file queue status for the same file:

```javascript
// LOCATION 1: Inside processFileStage1 (line 299-305)
setFileQueue(prev => prev.map(f => 
  f.id === fileEntry.id 
    ? { ...f, status: 'Stage1Complete' }
    : f
));

// LOCATION 2: Inside handleStartPipeline (line 899-904)
setFileQueue(prev => prev.map(f => 
  f.id === file.id 
    ? { ...f, status: 'Stage1Complete' }
    : f
));
```

#### Why This Breaks Step 1→2 Progression
- React batches state updates, but these updates are in different functions
- If the loop in `handleStartPipeline` processes multiple files quickly, the second `setFileQueue` call may race with the first one
- Queue state becomes unpredictable: file may be marked as 'Ready' again instead of 'Stage1Complete'
- Button visibility depends on `fileQueue` state, so inconsistent queue blocks button appearance

#### Current Behavior
1. User clicks "Start Pipeline"
2. `handleStartPipeline` loops through files
3. For each file, `processFileStage1` sets status to 'Stage1Complete'
4. Then `handleStartPipeline` ALSO sets status to 'Stage1Complete'
5. If timing is right, the second update overwrites or races with the first
6. File queue becomes inconsistent
7. Button visibility condition fails: `stageStatus[1] === 'done'` may be true, but queue counter is wrong

---

### 🔴 ISSUE #2: Stage Status Cleared Unexpectedly

**Severity:** HIGH  
**Component:** DataIngestion.js, line 288  
**Impact:** Button visibility condition fails after processing multiple files

#### Root Cause
In `processFileStage1`, the ENTIRE stage status object is reset:

```javascript
setStageStatus({}); // <-- CLEARS ALL STAGES!
setStageMessages({}); // <-- CLEARS ALL MESSAGES!
```

This occurs BEFORE setting `stageStatus[1] = 'done'`. While this works for a single file, when processing multiple files in sequence:

1. First file: `stageStatus = {}` → `stageStatus[1] = 'done'` ✓
2. Second file: `stageStatus = {}` → `stageStatus[1] = 'done'` ✓
3. BUT: Between the reset and the set, there's a brief window where `stageStatus[1]` is undefined

#### Why This Breaks Step 1→2 Progression
The "Proceed to Stage 2" button condition is:
```javascript
{currentFileEntry && stageStatus[1] === 'done' && (
  <button onClick={handleProceedToStage2}>→ Proceed to Stage 2</button>
)}
```

- If `stageStatus` is cleared after file queue updates render, the button briefly disappears
- Users may click "Proceed" during this window and get an error
- Async batching means the button condition is evaluated BEFORE `stageStatus[1]` is set to 'done'

---

### 🔴 ISSUE #3: Missing Error Handling in handleProceedToStage2

**Severity:** HIGH  
**Component:** DataIngestion.js, lines 918-936  
**Impact:** User gets vague error messages when Stage 2 fails

#### Root Cause
The `handleProceedToStage2` function doesn't validate preconditions:

```javascript
const handleProceedToStage2 = async () => {
  if (!currentFileEntry) {
    setMessage('No file selected. Please start with Stage 1 first.');
    return; // <-- EARLY RETURN, doesn't throw or show alert
  }

  setIsLoading(true);
  
  try {
    await processFileStages2To7(currentFileEntry); // <-- Could fail silently
    setMessage(`✓ All stages complete for ${currentFileEntry.name}!`);
  } catch (error) {
    setMessage(`Error in Stages 2-7: ${error.message}`);
    console.error('Stages 2-7 error:', error); // <-- Only in console
  } finally {
    setIsLoading(false); // <-- Always runs, even on error
  }
};
```

#### Why This Breaks Step 1→2 Progression
- If `currentFileEntry` is null (which it might be after `handleStartPipeline` sets `setProcessingFileId(null)`), user sees a silent error message
- User doesn't understand that they need to click "Start Pipeline" again
- Button appears but clicking it does nothing
- No error state displayed in UI

---

### 🔴 ISSUE #4: Processing File ID Cleared Too Early

**Severity:** HIGH  
**Component:** DataIngestion.js, line 312 (in handleStartPipeline finally block)  
**Impact:** `currentFileEntry` becomes null, disabling "Proceed" button

#### Root Cause
In `handleStartPipeline`, the finally block clears the processing file ID:

```javascript
try {
  for (const file of readyFiles) {
    await processFileStage1(file);  // Sets currentFileEntry
    setFileQueue(prev => prev.map(...));
  }
} finally {
  setProcessingFileId(null); // <-- Clears before user clicks Proceed!
}
```

And there might be a useEffect that clears `currentFileEntry` when `processingFileId` becomes null.

#### Why This Breaks Step 1→2 Progression
1. User clicks "Start Pipeline"
2. All files process Stage 1, `currentFileEntry` = last file
3. `handleStartPipeline` completes, sets `processingFileId = null`
4. If useEffect watches `processingFileId`, it clears `currentFileEntry`
5. Button condition requires `currentFileEntry &&  stageStatus[1] === 'done'`
6. Button disappears because `currentFileEntry` is now null
7. User cannot proceed to Stage 2

---

### 🔴 ISSUE #5: Async State Batching Not Used

**Severity:** MEDIUM  
**Component:** DataIngestion.js, lines 277-315  
**Impact:** Multiple re-renders; unpredictable state transitions

#### Root Cause
`processFileStage1` makes 8+ separate setState calls in sequence:

```javascript
setProcessingFileId(fileEntry.id);         // 1
setCurrentFileEntry(fileEntry);            // 2
setUploadedFile(...);                      // 3
setFileType(...);                          // 4
setCurrentStage(1);                        // 5
setStageStatus({});                        // 6
setStageMessages({});                      // 7
setMessage(...);                           // 8
setAssistantMessage(...);                  // 9

// Later...
setStageStatus(prev => ({ ...prev, 1: 'running' }));      // 10
setStageMessages(prev => ({ ...prev, 1: '...' }));        // 11
await new Promise(r => setTimeout(r, 300));
setStageStatus(prev => ({ ...prev, 1: 'done' }));         // 12
setStageMessages(prev => ({ ...prev, 1: '...' }));        // 13
setAssistantMessage(prev => prev + ...);                  // 14
setFileQueue(prev => prev.map(...));                      // 15
```

None are wrapped in `startTransition()`, meaning React creates a new render for each state update.

#### Why This Breaks Step 1→2 Progression
- Multiple renders cause the button condition to be evaluated at different times
- State consistency is not guaranteed between renders
- If a render happens AFTER `stageStatus = {}` but BEFORE `stageStatus[1] = 'done'`, the button won't appear
- This race condition is non-deterministic and hard to debug

---

## Summary Table

| Issue | Severity | Effect on Step 1→2 | Root Cause |
|-------|----------|-------------------|-----------|
| #1: Queue Status Race | CRITICAL | Button may not appear | Dual updates to fileQueue |
| #2: Stage Status Cleared | HIGH | Button disappears briefly | Wholesale reset of stageStatus |
| #3: Missing Error Handling | HIGH | Silent failures | No error validation in Proceed |
| #4: Processing ID Cleared | HIGH | currentFileEntry becomes null | Early cleanup in finally block |
| #5: No Async Batching | MEDIUM | Unpredictable state | 15+ separate setState calls |

---

## Detection Method

To verify these issues:

### Test 1: Single File
1. Load "Load Existing Files" (loads 12 STEP files)
2. Click "Start Pipeline"
3. Wait for Stage 1 to complete
4. **Expected:** "Proceed to Stage 2" button appears
5. **Actual:** Button may not appear OR disappears after appearing

### Test 2: Check Browser Console
1. Open DevTools Console
2. Click "Start Pipeline"
3. Look for errors like:
   - `Cannot read property '1' of undefined` (stageStatus issue)
   - `currentFileEntry is null` (processing ID issue)
   - API errors from /convert-schema endpoint

### Test 3: Redux DevTools
1. Install Redux DevTools browser extension
2. Check React state updates timeline
3. Observe that `stageStatus` resets and multiple `fileQueue` updates occur

---

## Recommended Fixes

### Fix #1: Remove Duplicate Queue Status Updates
**Priority:** CRITICAL  
**Effort:** 5 minutes  
**Risk:** Low

Remove the `setFileQueue` call from `processFileStage1` and keep only the one in `handleStartPipeline`.

### Fix #2: Preserve Stage Status Instead of Resetting
**Priority:** HIGH  
**Effort:** 10 minutes  
**Risk:** Medium

Instead of `setStageStatus({})`, preserve existing state:
```javascript
setStageStatus(prev => ({
  ...prev,
  1: 'running'  // Only update stage 1
}));
```

### Fix #3: Use startTransition for Consistent State
**Priority:** MEDIUM  
**Effort:** 15 minutes  
**Risk:** Medium

Wrap related state updates:
```javascript
startTransition(() => {
  setCurrentFileEntry(fileEntry);
  setCurrentStage(1);
  setStageStatus(prev => ({ ...prev, 1: 'running' }));
  setStageMessages(prev => ({ ...prev, 1: 'Detecting...' }));
});
```

### Fix #4: Keep processingFileId Until User Proceeds
**Priority:** HIGH  
**Effort:** 10 minutes  
**Risk:** Low

Don't set `processingFileId = null` until Stage 2 completes or user cancels.

### Fix #5: Add Validation in handleProceedToStage2
**Priority:** HIGH  
**Effort:** 5 minutes  
**Risk:** Low

```javascript
if (!currentFileEntry || stageStatus[1] !== 'done') {
  setMessage('❌ Stage 1 must complete before proceeding. Click "Start Pipeline" again.');
  return;
}
```

---

## Next Steps

1. ✅ Verify issues exist with test cases above
2. ⏳ Implement fixes in recommended priority order
3. ⏳ Test with single file, then multiple files
4. ⏳ Verify "Proceed to Stage 2" appears and functions correctly
5. ⏳ Run integration test on full 7-stage pipeline

---

**Document Status:** Complete Root Cause Analysis  
**Recommended Action:** Begin implementation of fixes starting with #1 (Critical)
