# Cycle 3 explore: FLEx parser priority + ActiveParser

Repos read: FieldWorks (branch `main`, with UNCOMMITTED local mods to ParserScheduler.cs / ParserWorker.cs), liblcm. Both present.

## 1. ParserPriority — 5 members, all explicit
`D:\Github\_Projects\_LEX\FieldWorks\Src\LexText\ParserCore\ParserScheduler.cs:25-32`
```
ReloadGrammarAndLexicon = 0, TryAWord = 1, High = 2, Medium = 3, Low = 4
```
Lower int = served first (see Q2). Assignment sites:
- ReloadGrammarAndLexicon: ParserScheduler.cs:238 (`ReloadGrammarAndLexicon()`), ctor ParserScheduler.cs:153.
- TryAWord: ParserScheduler.cs:347 (`ScheduleOneWordformForTryAWord`), work class at :83.
- High: ParserUI\ParserListener.cs:145 (`PropChanged` — wordform edited live) and :493 (`OnParseCurrentWord`).
- Medium: ParserListener.cs:529 (`OnParseWordsInCurrentText`), :543 (`OnParseUnapprovedWordsInCurrentText`), :576 (`OnCheckParserOnCurrentText`), :616 (`OnCheckParserOnGenre`).
- Low: ParserListener.cs:655 (`OnCheckParserOnAll`), :990 (`OnParseAllWords`), :1102 (`OnReparseAllWords`); also ToneParsInvoker.cs:690.
Path: ParserListener -> ParserConnection.cs:100/106 -> ParserScheduler.cs:350-363 -> `m_thread.EnqueueWork(priority, ...)`.

## 2. Queue jump, NOT preemption
Priority is only a `PriorityQueue` key: `ConsumerThread<ParserPriority, ParserWork>` (ParserScheduler.cs:135,152). `PriorityQueue` is a `SortedDictionary<P, LinkedList<T>>` (liblcm\src\SIL.LCModel.Utils\PriorityQueue.cs:32,48) and `Dequeue` takes `m_queues.First()` (PriorityQueue.cs:161-166) — i.e. numerically lowest enum value first. `WorkLoop` (ConsumerThread.cs:434-453) calls the handler and only re-checks the queue after it returns; there is no cancel/abort/interrupt of in-flight work. So a High request enqueued while a Low one is running waits for that item to finish. Granularity is one wordform (`UpdateWordformWork.DoWork`, ParserScheduler.cs:110-114), so the wait is short.
CAVEAT (local fork mod, uncommitted): ParserScheduler.cs:265-296 `Work()` now drains the WHOLE queue via `GetAllWorkItems()` and runs it through `Parallel.ForEach` for HC/XAmple — inside a drained batch, priority ordering is effectively lost. Upstream serial path survives only as fallback (:292-295).

## 3. ActiveParser — CAN change live; do NOT cache per session
Implementation: liblcm\src\SIL.LCModel\DomainImpl\OverridesLing_MoClasses.cs:4197-4245 (get/set over `ParserParameters` XML; getter defaults to `"XAmple"` on any parse failure, :4213). Interface: liblcm\src\SIL.LCModel\InterfaceAdditions.cs:5926-5930 (get AND set).
WRITES: ParserUI\ParserListener.cs:1117-1133 `OnChooseParser` — user menu, wired at DistFiles\Language Explorer\Configuration\Words\areaConfiguration.xml:26-31,297-300 ("Default Parser (XAmple)" / "Phonological Rule-based Parser (HermitCrab.NET)"); it calls `DisconnectFromParser()` then sets the value in a NonUndoableUnitOfWork. Also ToneParsFLExForm.cs:716,726 (temporarily flips to XAmple and back).
READS: ParserWorker.cs:65, FdoLexicon.cs:646, TryAWordDlg.cs:479, ParserListener.cs:1113, ToneParsFLExForm.cs:679, OverridesLangProj.cs:224.
=> Re-read per call.

## 4. ParserWorker.cs throw (exact, lines 65-77)
```
switch (m_cache.LanguageProject.MorphologicalDataOA.ActiveParser)
{
    case "XAmple":
        m_parser = new XAmpleParser(cache, dataDir);
        agent = ...kguidAgentXAmpleParser); break;
    case "HC":
        m_parser = new HCParser(cache);
        agent = ...kguidAgentHermitCrabParser); break;
    default:
        throw new InvalidOperationException("The language project is set to use an unrecognized parser.");
}
```
Accepted values: exactly `"XAmple"` and `"HC"`, case-sensitive. Identical switch at FdoLexicon.cs:646-655.
