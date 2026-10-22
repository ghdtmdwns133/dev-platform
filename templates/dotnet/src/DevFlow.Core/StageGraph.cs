using System.Collections.ObjectModel;

namespace DevFlow.Core;

public sealed record Stage(string Name, int Duration, IReadOnlyList<string> Needs);

public static class StageGraph
{
    public static IReadOnlyList<string> TopologicalOrder(IEnumerable<Stage> stages)
    {
        ArgumentNullException.ThrowIfNull(stages);

        var list = stages.ToList();
        var needs = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        foreach (var stage in list)
        {
            needs[stage.Name] = stage.Needs;
        }

        var pending = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var (name, dependencies) in needs)
        {
            foreach (var dependency in dependencies)
            {
                if (!needs.ContainsKey(dependency))
                {
                    throw new ArgumentException(
                        $"Unknown stage dependency '{dependency}' of '{name}'.",
                        nameof(stages)
                    );
                }
            }

            pending[name] = dependencies.Count;
        }

        var ready = new List<string>(
            pending.Where(pair => pair.Value == 0).Select(pair => pair.Key)
        );
        ready.Sort(StringComparer.Ordinal);
        var order = new List<string>(list.Count);
        while (ready.Count > 0)
        {
            var name = ready[0];
            ready.RemoveAt(0);
            order.Add(name);
            foreach (var (candidate, dependencies) in needs)
            {
                if (!dependencies.Contains(name))
                {
                    continue;
                }

                pending[candidate]--;
                if (pending[candidate] == 0)
                {
                    ready.Add(candidate);
                }
            }

            ready.Sort(StringComparer.Ordinal);
        }

        if (order.Count != needs.Count)
        {
            throw new ArgumentException("Stage graph contains a cycle.", nameof(stages));
        }

        return new ReadOnlyCollection<string>(order);
    }

    public static int CriticalPathLength(IEnumerable<Stage> stages)
    {
        ArgumentNullException.ThrowIfNull(stages);

        var list = stages.ToList();
        var order = TopologicalOrder(list);
        var byName = new Dictionary<string, Stage>(StringComparer.Ordinal);
        foreach (var stage in list)
        {
            byName[stage.Name] = stage;
        }

        var finish = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var name in order)
        {
            var stage = byName[name];
            var longest = 0;
            foreach (var need in stage.Needs)
            {
                longest = Math.Max(longest, finish[need]);
            }

            finish[name] = longest + stage.Duration;
        }

        var total = 0;
        foreach (var value in finish.Values)
        {
            total = Math.Max(total, value);
        }

        return total;
    }
}
