using DevFlow.Core;
using Xunit;

namespace DevFlow.Core.Tests;

public sealed class StageGraphTests
{
    private static readonly string[] _buildNeeds = ["build"];
    private static readonly string[] _testNeeds = ["test"];
    private static readonly string[] _needsB = ["b"];
    private static readonly string[] _needsA = ["a"];
    private static readonly string[] _expectedOrder = ["build", "lint", "test", "package"];

    [Fact]
    public void CriticalPathLengthUsesLongestDependencyChain()
    {
        var stages = new[]
        {
            new Stage("build", 4, Array.Empty<string>()),
            new Stage("test", 3, _buildNeeds),
            new Stage("package", 2, _testNeeds),
            new Stage("lint", 1, _buildNeeds),
        };

        Assert.Equal(9, StageGraph.CriticalPathLength(stages));
        Assert.Equal(_expectedOrder, StageGraph.TopologicalOrder(stages));
    }

    [Fact]
    public void CriticalPathLengthOfEmptyGraphIsZero()
    {
        Assert.Equal(0, StageGraph.CriticalPathLength(Array.Empty<Stage>()));
    }

    [Fact]
    public void TopologicalOrderRejectsCycles()
    {
        var stages = new[]
        {
            new Stage("a", 1, _needsB),
            new Stage("b", 1, _needsA),
        };

        var error = Assert.Throws<ArgumentException>(() => StageGraph.TopologicalOrder(stages));
        Assert.Contains("cycle", error.Message, StringComparison.Ordinal);
    }
}
