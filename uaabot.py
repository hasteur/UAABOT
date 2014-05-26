import wikipedia as pywikibot
import config
import catlib
from pywikibot import i18n
import userlib
import datetime
class CategoryListifyRobot:
    '''Creates a list containing all of the members in a category.'''
    def __init__(self):
        self.site = pywikibot.getSite()
        self.cat = catlib.Category(self.site, 'Category:Wikipedia usernames with possible policy issues')
        self.recurse = False
        self.run_time = datetime.datetime.now() + datetime.timedelta(days=-7)
        self.sentinel_text = '[[Category:Wikipedia usernames with possible policy issues|{{PAGENAME}}]]'

    def run(self):
        listOfArticles = self.cat.articlesList(recurse=self.recurse)
        for article in listOfArticles:
          #Do Something!
          print article
          self.evaluateUAA(article)
          pass

    def evaluateUAA(self,user_page):
      if 'User talk:' not in user_page.title():
        return
      page_history = user_page.fullVersionHistory()
      page_history_check = True
      for page_revision in page_history:
        page_date = datetime.datetime.strptime(
          page_revision[1],
          "%Y-%m-%dT%H:%M:%SZ"
        )
        if page_date >= self.run_time:
          if self.sentinel_text not in page_revision[3]:
            page_history_check = False
            break
        else:
          #Ok traversed down the history, now to check the 1st rev outside 7 days
          if self.sentinel_text not in page_revision[3]:
            page_history_check = False
          break
        if page_history_check == True:
          #Ok, cat has been on for length, now to see if the editor has edited
          # in 7 days
          user_name = user_page.titleWithoutNamespace()
          user_obj = userlib.User(self.site,user_name)
          last_edit_date = None
          try:
              latest_rev = user_obj.contributions().next()
              last_edit_date = datetime.datetime.strptime(
                latest_rev[2],
                "%Y%m%d%H%M%S"
              )
          except StopIteration:
            #Hrm... User has no publically visible actions.
            #Hack a solution in to
            last_edit_date = self.run_time
          if last_edit_date <= self.run_time:
            #Ok, user hasn't edited in the same 7 day window, this is now
            # a stale report
            page_text = user_page.get()
            replace_text = page_text.replace(self.sentinel_text,'')
            print user_page
      return 
def main():
  clb = CategoryListifyRobot()
  clb.run()

if __name__ == "__main__":
  main()
   
