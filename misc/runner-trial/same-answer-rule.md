# Runner trial: the "same answer" rule

Repo line cites are at commit 7efa0776.

This rule says which fields are compared between two runs, and how times and counts are normalised. It is needed because eks-recon reads live state and names its output with a timestamp. The trial uses it for T7 (cases.md).

## The rule

Two runs, or two runners, give the same answer on a case when all of these hold:

1. **Pass or fail.** Both runs give the same result on the case's single pass condition (cases.md).
2. **Verdict or rating cases (T1, T4).** The same verdict word, and the same named items (blocker ids, component names, versions). Items are compared as sets, so order is ignored.
3. **Report artifact cases (T2, T7).** The same set of facts after normalising. T7's compared fields (misc/evals/eks-recon/evals.json:8-11): the cluster version and platform version, the primary compute strategy, the EKS-managed add-ons with their installed versions, and the IaC tool managing the cluster.
   - Removed before comparing: timestamps, report file names with dates, durations, run ids and request ids.
   - Counts of live objects (pods, events, node ages) are compared only where the case names them.
   - Ignored: whitespace, table column order and heading wording.
   - Compared: row values.
   - A compared field whose live value changed between the two runs (a node group that scaled, an add-on updated between runs) is skipped, not counted as a different answer, and both values are logged with the run ids. A change in the cluster is not a disagreement between runs. A pair of runs with more than one skipped field reads "cannot compare", not "same answer".
   - Three runs give the same answer when each of their three pairs does; if any pair reads 'cannot compare', the three runs read 'cannot compare'.
   - A run marked cannot-run (it could not read the cluster) leaves each pair it is in at 'cannot compare', so an arm with any cannot-run run reads 'cannot compare'.
4. **Generated project cases (T3).** The same validator result. File contents are not compared, so two different valid projects count as the same answer.
5. **Free prose** outside the compared fields is not compared.

For T5 and T6, rule 1 alone applies: each has a pass condition and no compared fields.
