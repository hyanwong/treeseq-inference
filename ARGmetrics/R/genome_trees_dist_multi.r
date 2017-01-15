#' Use tree metrics to compare multiple inferred ancestries (ARGs) over a genomic region
#'
#' Runs genome.trees.dist to compare multiple ancestry estimates against a known original
#' See ?genome.trees.dist for more information.
#' @param treeseq.base The base multiPhylo object, or a path to a .nex file
#' @param treeseq.multi A list of n multiPhylo objects (or list of n paths to .nex files).
#' @param weights If provided, these are treated as weights, and instead of returning a matrix
#' with columns for each measure, and n rows, a single row is returned giving the distance
#' measures averaged over all the different tree sequences. Set to 1 for a "standard" unweighted average
#' @param acceptable.length.diff.pct How much difference in sequence length is allows between the 2 trees? (Default: 0.1 percent)
#' @param variant.positions A list of positions of each variant (not implemented)
#' @export
#' @examples
#' genome.trees.dist.multi()

genome.trees.dist.multi <- function(treeseq.base, treeseq.multi, weights=NULL, acceptable.length.diff.pct = 0.1, variant.positions=NULL) { 
    if (class(treeseq.multi) == "multiPhylo") {
        stop("treeseq.multi should contain a *list* of multiPhylo objects, not simply a single multiPhylo object.")
    }
    if (randomly.resolve.polytomies != FALSE) {
        set.seed(randomly.resolve.polytomies)
        randomly.resolve.polytomies = TRUE
    }
    metrics <- do.call(rbind,lapply(treeseq.multi, 
                                    genome.trees.dist, 
                                    treeseq.base,
                                    acceptable.length.diff.pct = acceptable.length.diff.pct,
                                    variant.positions = variant.positions))
    if (is.numeric(weights)) {
        return(colSums(metrics * weights)/sum(weights))
    } else {
        return(metrics)
    }
}