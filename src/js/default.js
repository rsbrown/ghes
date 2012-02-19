var path,
    parts,
    accountName,
    repoName,
    repoId,
    pagePullRequestNumber;

var appendLinks = function(repoPullRequests) {
  var prevPullNumber,
      nextPullNumber;

  for (i in repoPullRequests) {
    var pullReq = repoPullRequests[i];
    if (pullReq.number === pagePullRequestNumber) {
      
      var index          = parseInt(i),
          prevPullNumber = repoPullRequests[index+1] ? repoPullRequests[index+1].number : null,
          nextPullNumber = repoPullRequests[index-1] ? repoPullRequests[index-1].number : null,
          // navElement     = $("<div>" +
          //                     "<span style='font-size: 25px'>" + 
          //                      "<a href=\"" + parts[0] + prevPullNumber + "/files" + "\" class=\"pullreqnav\">&laquo;</a>" + 
          //                     "</span>" + 
          //                     "<span style='padding:0 3px;'>|</span>" + 
          //                     "<span style='font-size: 25px'>" + 
          //                      "<a href=\"" + parts[0] + nextPullNumber + "/files" + "\"class=\"pullreqnav\">&raquo;</a>" + 
          //                     "</span>" + 
          //                    "</div>");

          // navElement           = $("<div></div>"),
          prevLinkElement          = $("<li style='font-size: 25px'><a href=\"" + parts[0] + prevPullNumber + "/files" + "\" class=\"pullreqnav\">&laquo;</a></li>"),
          nextLinkElement          = $("<li style='font-size: 25px'><a href=\"" + parts[0] + nextPullNumber + "/files" + "\"class=\"pullreqnav\">&raquo;</a></li>"),
          dividerElement           = $("<li style='padding:0 3px;'>|</li>");

      if (nextPullNumber) {
        $(".pagehead-actions").prepend(nextLinkElement);
      }

      if (prevPullNumber && nextPullNumber) {
        $(".pagehead-actions").prepend(dividerElement);
      }

      if (prevPullNumber) {
        $(".pagehead-actions").prepend(prevLinkElement);
      }
      
      break;
    }
  }
};

var fetchMorePullRequests = function(repoPullRequests, repoId) {
  var pageNum = 1;
  forge.request.get(
    "https://api.github.com/repos/" + accountName + "/" + repoName + "/pulls?page=" + pageNum + "&per_page=100", 
    function(response) {
      repoPullRequests[repoId] = response;
      forge.prefs.set("pull_requests", repoPullRequests);
      appendLinks(repoPullRequests[repoId]);
    },
    function(response) {
      console.log("error retrieving list of pull requests", response);
    }
  );
};

var appendPullRequestNavLinks = function() {
  path                  = document.location.pathname;
  parts                 = path.split(/\d+/);
  accountName           = $(".title-actions-bar").find("span[itemprop='title']").html();
  repoName              = $(".title-actions-bar").find(".js-current-repository").html();
  repoId                = accountName + "/" + repoName;
  pagePullRequestNumber = parseInt(path.replace(parts[0], '').replace(parts[1], ''));
  
  forge.prefs.get("pull_requests", function(repoPullRequests) {
    repoPullRequests = repoPullRequests || {};
    if (repoPullRequests[repoId] === undefined) {
      repoPullRequests[repoId] = [];
      
    }
    
    if (repoPullRequests[repoId].length > 0) {
      appendLinks(repoPullRequests[repoId]);
    } else {    
      fetchMorePullRequests(repoPullRequests, repoId);
    }    
  });

};

$(function(){
  appendPullRequestNavLinks();

  // TODO: use parts[1] to stay on te same page context user is currently on
  //
  // $(".js-hard-tabs li a:not(.pullreqnav)").click(function(e){
  //   console.log("it's happening");
  //   $(".pullreqnav").remove();
  //   appendNavLinks();
  // });  
});
