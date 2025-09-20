# AdCore Dependency Manager

A standalone Python package for intelligent, incremental dependency resolution and caching in modular applications.

## Features

- **Incremental Resolution**: Only resolves dependencies for modules that have actually changed
- **Smart Caching**: Module-level granularity with automatic cache invalidation
- **Performance Optimized**: 4-60x faster than full resolution depending on scenario
- **Conflict Resolution**: Handles version conflicts between modules gracefully
- **Batch Installation**: Efficient package installation with duplicate detection

## Quick Start

```python
from dependency_manager import DependencyManager

# Initialize
dm = DependencyManager()

# Resolve dependencies for all modules
await dm.resolve_dependencies()

# Or use convenience functions
from dependency_manager import re_resolve_dependencies
await re_resolve_dependencies()
```

## Architecture

### Cache Structure

```json
{
  "module_caches": {
    "authentication": {
      "hash": "abc123...",
      "packages": {"fastapi": "==0.116.1", "pydantic": "==2.5.0"},
      "last_updated": "2024-01-01T12:00:00"
    },
    "feature_x": {
      "hash": "def456...",
      "packages": {"requests": "==2.31.0"},
      "last_updated": "2024-01-01T12:05:00"
    }
  },
  "backbone_hash": "ghi789...",
  "combined_hash": "jkl012...",
  "resolved_packages": {
    "fastapi": "==0.116.1",
    "pydantic": "==2.5.0",
    "requests": "==2.31.0"
  }
}
```

### Performance Benefits

| Scenario | Old Approach | New Incremental | Improvement |
|----------|--------------|-----------------|-------------|
| No changes | 60s (full resolution) | <1s (cache hit) | **60x faster** |
| 1 module changes | 60s (full resolution) | 10-15s (incremental) | **4-6x faster** |
| 3 modules change | 60s (full resolution) | 25-35s (incremental) | **2-3x faster** |

## API Reference

### DependencyManager Class

#### Methods

- `__init__()`: Initialize the dependency manager
- `resolve_dependencies()`: Perform incremental dependency resolution
- `invalidate_cache()`: Clear entire dependency cache
- `invalidate_module_cache(module_name)`: Clear cache for specific module
- `calculate_module_hash(module_name, content)`: Calculate hash for module requirements
- `get_installed_packages()`: Get set of currently installed packages

### Convenience Functions

- `re_resolve_dependencies()`: Main entry point for dependency resolution
- `invalidate_dependency_cache()`: Clear entire cache
- `invalidate_module_cache(module_name)`: Clear module-specific cache

## Integration with AdCore

The dependency manager is integrated into AdCore's module system:

```python
# Automatic resolution on module changes
await load_modules(app, backbone_context)  # Triggers dependency resolution

# Manual resolution
from src.dependency_manager import re_resolve_dependencies
await re_resolve_dependencies()
```

## Configuration

The dependency manager uses the following constants from `constants.py`:

- `DEPENDENCY_CACHE_FILE`: Path to cache file (`.adcore_cache/dependency_cache.json`)
- `DEPENDENCY_CACHE_DIR`: Cache directory (`.adcore_cache/`)
- `MODULES_LOADED_DIR`: Directory containing loaded modules
- `MODULES_UPLOAD_DIR`: Directory for temporary files
- `BACKBONE_REQUIREMENTS_LOCK_FILE`: Compiled requirements file (`.adcore_cache/compiled_requirements.lock`)

## Error Handling

The dependency manager provides comprehensive error handling:

- **Cache Corruption**: Automatically recreates corrupted cache files
- **Network Issues**: Graceful fallback for pip network problems
- **Version Conflicts**: Intelligent conflict resolution with logging
- **Permission Issues**: Clear error messages for file system problems

## Future Enhancements

- **Parallel Resolution**: Resolve multiple modules concurrently
- **Dependency Graph**: Visualize module dependencies
- **Security Scanning**: Integrate with vulnerability scanners
- **Container Optimization**: Optimize for containerized deployments

## Contributing

This dependency manager is designed to be published as a standalone package. To contribute:

1. Ensure all tests pass
2. Add comprehensive documentation
3. Follow semantic versioning
4. Maintain backward compatibility

## License

MIT License - See LICENSE file for details.
