import argparse
import logging
from slides_manager import GoogleWorkspaceManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Cleanup Duplicate Slides")
    parser.add_argument("--force", action="store_true", help="Actually delete files. Default is dry-run.")
    parser.add_argument("--target", default="Copy of", help="String to search for in filenames (default: 'Copy of')")
    args = parser.parse_args()

    manager = GoogleWorkspaceManager()
    
    logger.info(f"🔍 Searching for presentations containing: '{args.target}'")
    files = manager.search_presentations(args.target)
    
    if not files:
        logger.info("✅ No matching files found.")
        return

    logger.info(f"found {len(files)} candidates:")
    for f in files:
        logger.info(f" - {f['name']} (ID: {f['id']})")
    
    if not args.force:
        logger.info("\n🚧 DRY RUN MODE. Use --force to delete.")
    else:
        logger.info(f"\n🗑️ DELETING {len(files)} files...")
        for f in files:
            manager.delete_file(f['id'])
        logger.info("✅ Cleanup complete.")

if __name__ == "__main__":
    main()
